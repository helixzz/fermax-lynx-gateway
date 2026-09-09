"""Live gateway orchestration. All building I/O is owned by one worker thread."""
from contextlib import nullcontext
import collections
import logging
import queue
import socket
import threading
import time
import uuid
from pathlib import Path

from .media import Video
from .sip_live import Signaling
from .transport import Transport
from .identity import Announcer

class Controller:
    def __init__(self, state, codec):
        self.state, self.codec = state, codec
        self.own = state.config['monitor_ip']
        self.panels = {p['id']:p['ip'] for p in state.config['panels']}
        self.names = {p['ip']:p['name'] for p in state.config['panels']}
        self.actions = queue.Queue(maxsize=16)
        self.stop = threading.Event()
        self.hosts, self.sockets = [], []
        self.video = Video(codec, state)
        self.sip = None
        self.operations = collections.deque()
        self.pending_op = None
        self.auto_attempted = False
        self.remote = None
        self.last_keep = 0
        self.keep_pending = None
        self.control_peer = self.keep_peer = None
        self.link_checked = 0

    def enqueue(self, action, panel, request_id, expected_call=None, phone=False, guard=None):
        try:
            self.actions.put_nowait((action, panel, request_id, expected_call, phone, guard))
        except queue.Full:
            raise ValueError('操作队列已满')

    def send_sip(self, data, remote):
        self.sockets[0].sendto(self.codec.encrypt(data), (remote, 5060))

    def begin(self, remote):
        self.remote = remote
        self.auto_attempted = False
        self.operations.clear()
        self.pending_op = None
        self.control_peer = self.client.connect(remote, 52102)
        self.keep_peer = self.client.connect(remote, 57703)
        self.last_keep, self.keep_pending = 0, None
        self.video.reset()
        with self.state.lock:
            self.state.panel = self.names[remote]
            self.state.relays, self.state.allow_open = [], False
        self.operations.append(('panelGetRelaysCommand', {'doormatic':False}, 'panelGetRelaysResponse', 'relays', None))
        self.operations.append(('panelGetAllowOpenDoorFlagCommand', {'dummy':True}, 'panelGetAllowOpenDoorFlagResponse', 'permission', None))

    def notify(self, kind, value):
        with self.state.lock:
            if kind in ('incoming','outgoing'):
                self.begin(value)
                self.state.call_id = uuid.uuid4().hex
                self.state.panel_id = next(k for k,v in self.panels.items() if v == value)
                self.state.direction = kind
                self.state.call = 'ringing'
                self.state.event(('门铃呼入：' if kind == 'incoming' else '正在查看：')+self.names[value], kind)
            elif kind in ('early_video','audio','ending'):
                self.state.call = kind
                if kind == 'ending': self.state.gateway_audio.end()
                if kind == 'audio':
                    self.state.event('已接听', 'answered')
                elif kind == 'early_video':
                    self.state.event('视频会话已建立', 'video_session')
            elif kind == 'ended':
                self.state.event('通话结束', 'call_ended', value)
                self.state.call, self.state.panel = 'idle', None
                self.state.call_id = self.state.panel_id = self.state.direction = None
                self.state.allow_open, self.state.relays = False, []
                self.operations.clear()
                self.pending_op = self.keep_pending = None
                for peer in (self.control_peer, self.keep_peer):
                    if peer is not None:
                        address = self.client.address(peer)
                        self.client.pending.pop(address, None)
                        self.client.peers.pop(address, None)
                        peer.disconnect_now()
                self.control_peer = self.keep_peer = None
                self.remote = None
                self.video.reset()
            elif kind == 'error':
                self.state.event(value, 'error')

    def setup(self):
        self.sockets = []
        for port in (5060, 16402):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sockets.append(sock)
            sock.bind((self.own, port))
            sock.setblocking(False)
        self.client = Transport(self.codec, bind=self.own, allowed=self.panels.values())
        self.hosts.append(self.client)
        for port in (52102, 56102, 57703):
            self.hosts.append(Transport(self.codec, port=port, bind=self.own, allowed=self.panels.values()))
        publisher=Transport(self.codec,bind=self.own,allowed=self.panels.values())
        self.hosts.append(publisher)
        self.announcer=Announcer(publisher,self.codec,self.state.config,self.state.event)
        self.sip = Signaling(self.own, self.panels.values(), self.send_sip, self.notify, unit=self.state.config['unit'])
        with self.state.lock:
            self.state.network = 'ready'
        self.state.event('门禁网络就绪', 'network_ready', {'ip':self.own})

    def close_network(self):
        for sock in self.sockets:
            sock.close()
        for host in self.hosts:
            host.close()
        self.sockets, self.hosts = [], []
        self.sip = None
        self.remote = None
        self.operations.clear()
        self.pending_op = None
        while True:
            try:
                action, panel, request_id = self.actions.get_nowait()[:3]
            except queue.Empty:
                break
            self.state.event('网络断开，操作已取消', 'control_failed', {'action':action,'request_id':request_id})
        with self.state.lock:
            self.state.call, self.state.panel = 'idle', None
            self.state.call_id = self.state.panel_id = self.state.direction = None
            self.state.allow_open, self.state.relays = False, []
            self.state.network = 'disconnected'
        self.video.reset()

    def open(self, automatic=False, request_id=None, guard=None):
        with self.state.lock:
            if not self.sip.dialog or not self.sip.dialog.acked or not self.state.allow_open or not self.state.relays:
                raise ValueError('门口机尚未允许开门')
            if any(op[3].startswith('open') for op in self.operations) or (self.pending_op and self.pending_op[1].startswith('open')):
                raise ValueError('开门请求正在处理')
            if automatic:
                self.operations.append(('panelGetRelaysCommand', {'doormatic':True}, 'panelGetRelaysResponse', 'auto_relays', None))
            else:
                context = {'call_id': self.state.call_id, 'panel_id': self.state.panel_id}
                self.operations.append(('panelOpenDoorCommand', {'relayName':self.state.relays[0], 'doormatic':False}, 'panelOpenDoorResponse', 'open_manual', request_id, guard, context))

    def result(self, purpose, pending, request_id=None):
        if pending.error:
            self.state.event('开门结果未知，请现场确认' if purpose.startswith('open') else '门口机请求失败：'+purpose,
                             'open_unknown' if purpose.startswith('open') else 'protocol_error', {'reason':pending.error, 'request_id':request_id})
            with self.state.lock:
                self.state.allow_open = False
            return
        result = pending.result
        with self.state.lock:
            if purpose == 'relays':
                self.state.relays = result.get('relayTags', [])
            elif purpose == 'permission':
                self.state.allow_open = bool(result.get('allowOpenDoor'))
            elif purpose == 'auto_relays':
                relays = result.get('relayTags', [])
                if relays and self.state.policy['enabled'] and self.state.allow_open:
                    self.operations.appendleft(('panelOpenDoorCommand', {'relayName':relays[0], 'doormatic':True}, 'panelOpenDoorResponse', 'open_auto', None))
                else:
                    self.state.event('自动开门未执行：状态或权限已变化', 'auto_skipped')
            elif purpose.startswith('open'):
                success = result.get('result') == 'PANEL_OPEN_DOOR_RESULT_OK'
                name = '自动开门' if purpose == 'open_auto' else '手动开门'
                self.state.event(name+('成功' if success else '被拒绝'), purpose if success else 'open_denied', result | {'request_id':request_id})

    def service_operations(self):
        now = time.monotonic()
        if not self.sip.dialog or not self.remote or not self.sip.dialog.acked:
            return
        if self.pending_op:
            pending, purpose, request_id = self.pending_op
            if pending.result is not None or pending.error:
                self.pending_op = None
                self.result(purpose, pending, request_id)
        address = (self.remote, 52102)
        if self.operations and not self.pending_op and address in self.client.peers:
            operation = self.operations.popleft()
            command, fields, response, purpose, request_id = operation[:5]
            guard = operation[5] if len(operation) > 5 else None
            if purpose == 'open_auto' and not self.state.policy['enabled']:
                return
            try:
                with self.state.lock, guard(relay=fields.get('relayName')) if guard else nullcontext():
                    pending = self.client.request(self.client.peers[address], command, fields, response)
                    self.pending_op = (pending, purpose, request_id)
            except (ValueError, OSError, KeyError, TypeError):
                context = operation[6] if len(operation) > 6 else {}
                self.state.event('集成操作已取消：授权、会话或有效期已变化', 'control_failed', {'request_id': request_id, **context})
        if self.keep_pending and (self.keep_pending.error or self.keep_pending.result is not None):
            if self.keep_pending.error or not self.keep_pending.result.get('state'):
                self.sip.end('会话保活失败')
                return
            self.keep_pending = None
        keep_address = (self.remote, 57703)
        if not self.keep_pending and now-self.last_keep >= 1 and keep_address in self.client.peers:
            self.keep_pending = self.client.request(self.client.peers[keep_address], 'sessionKeepAliveCommand', {'dummy':True}, 'sessionKeepAliveResponse')
            self.last_keep = now
        d = self.sip.dialog
        if d and d.incoming and d.acked and not self.auto_attempted and now-d.created >= 4.4 and self.state.policy['enabled'] and self.state.allow_open and self.state.relays:
            self.auto_attempted = True
            self.open(True)

    def iteration(self):
        now = time.monotonic()
        if now-self.link_checked > 2:
            self.link_checked = now
            if (Path('/sys/class/net')/self.state.config['building_interface']/'carrier').read_text().strip() != '1':
                raise OSError('Ethernet carrier lost')
        for index, sock in enumerate(self.sockets):
            for _ in range(128):
                try:
                    data, address = sock.recvfrom(65535)
                except BlockingIOError:
                    break
                remote, port = address
                if remote not in self.panels.values():
                    continue
                if index == 0 and port == 5060:
                    try:
                        self.sip.receive(self.codec.decrypt(data), remote)
                    except (ValueError, KeyError, UnicodeError):
                        self.state.event('忽略无法解析的 SIP 报文', 'protocol_error')
                elif index == 1 and remote == self.remote and port == 5010:
                    self.video.feed(data)
        for host in self.hosts:
            for _ in range(32):
                event = host.poll()
                if not event:
                    break
                if event[0] != 'message':
                    continue
                _, peer, message = event
                events = message.get('[protobuffers.event]', {})
                caps = events.get('[protobuffers.panelCapabilitiesEvent]')
                if caps and peer.address.host == self.remote:
                    with self.state.lock:
                        self.state.allow_open = bool(caps.get('openDoorEnable'))
                commands = message.get('[protobuffers.command]', {})
                if '[protobuffers.sessionKeepAliveCommand]' in commands:
                    host.send(peer, self.codec.envelope('response','sessionKeepAliveResponse',{'state': bool(self.sip.dialog and peer.address.host == self.remote)}))
                push = commands.get('[protobuffers.pushDeviceCallCommand]')
                if push:
                    self.state.event('门口机通知：'+push.get('pushType',''), 'panel_notification', push)
        try:
            queued = self.actions.get_nowait()
            action, panel, request_id, expected_call, phone = queued[:5]
            guard = queued[5] if len(queued) > 5 else None
        except queue.Empty:
            pass
        else:
            try:
                with self.state.lock, guard() if guard else nullcontext():
                    if phone and action != 'preview' and expected_call != self.state.call_id:
                        raise ValueError('会话已变化，操作已取消')
                    if action == 'preview':
                        self.sip.preview(self.panels[panel or next(iter(self.panels))])
                    elif action == 'answer':
                        raise ValueError('远程语音尚未启用；可查看视频、开门或挂断')
                    elif action == 'open':
                        self.open(request_id=request_id, **({'guard': guard} if guard else {}))
                    elif action == 'hangup':
                        if self.pending_op and self.pending_op[1].startswith('open'):
                            raise ValueError('正在等待开门应答，请稍后挂断')
                        self.sip.hangup()
            except (ValueError, OSError, KeyError, TypeError) as error:
                detail = {'request_id':request_id}
                if phone and action != 'preview':
                    detail['call_id'] = expected_call
                if guard:
                    detail.update(panel_id=panel, call_id=expected_call)
                self.state.event(str(error), 'control_failed', detail)
        self.sip.tick()
        self.announcer.tick()
        self.service_operations()

    def run(self):
        reported = False
        while not self.stop.is_set():
            if self.sip is None:
                try:
                    self.setup()
                    reported = False
                except (OSError, MemoryError) as error:
                    self.close_network()
                    if not reported:
                        self.state.event('等待门禁网线连接', 'network_wait', {'error':str(error)})
                        reported = True
                    self.stop.wait(3)
                    continue
            try:
                self.iteration()
            except Exception:
                logging.exception('Live controller failed')
                self.state.event('门禁通信中断，正在重新连接', 'network_error')
                self.close_network()
                self.stop.wait(3)
            self.stop.wait(0.005)
        self.close_network()
        self.video.stop.set()
