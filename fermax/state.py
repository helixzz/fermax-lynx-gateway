"""Persistent policy, event journal and live controller facade."""
import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from .config import EXAMPLE, validate

DURATIONS = (15, 30, 60, 120, 240, 480, 720, 0)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.new')
    with temp.open('w', encoding='utf-8') as f:
        os.chmod(temp, 0o600)
        json.dump(value, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


class State:
    def __init__(self, folder, wall=time.time, mono=time.monotonic, config=None):
        self.lock = threading.RLock()
        self.wall, self.mono = wall, mono
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.config = validate(config or EXAMPLE)
        from .phone_preferences import PhonePreferences
        self.phone_preferences = PhonePreferences(self.folder)
        from .gateway_audio import GatewayAudio
        self.gateway_audio = GatewayAudio(self.folder,self.phone_preferences,mono=mono)
        self.ring_call_id = None
        self.call_started_mono = None
        self.call_ring_preferences = None
        self.path = self.folder/'policy.json'
        self.db = sqlite3.connect(self.folder/'events.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, time REAL NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, detail TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, action TEXT NOT NULL, time REAL NOT NULL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS events_kind_id ON events(kind,id)')
        self.db.commit()
        from .statistics import Statistics
        self.statistics = Statistics(self.db)
        self.policy = {'enabled': False, 'minutes': None, 'expires_at': None}
        self.deadline = None
        self.call, self.panel, self.relays = 'idle', None, []
        self.call_id, self.panel_id, self.direction = None, None, None
        self.stream_epoch = uuid.uuid4().hex
        self.stream_version, self.stream_signature = 0, None
        self.stream_slots = threading.BoundedSemaphore(12)
        self.allow_open = False
        self.controller = None
        self.video_jpeg, self.video_updated = None, 0
        self.notice, self.network = '正在启动门禁通信', 'connecting'
        self.clock_status = {'synchronized':False, 'source':'unknown', 'servers':[]}
        if self.path.exists():
            try:
                p = json.loads(self.path.read_text())
                if set(p) != {'enabled','minutes','expires_at'} or type(p['enabled']) is not bool:
                    raise ValueError('Invalid policy')
                if p['enabled'] and (type(p['minutes']) is not int or p['minutes'] not in DURATIONS):
                    raise ValueError('Invalid duration')
                if p['enabled'] and p['minutes'] != 0:
                    remaining = float(p['expires_at']) - self.wall()
                    if remaining <= 0 or remaining > p['minutes']*60:
                        raise ValueError('Expired policy or clock not synchronized')
                    self.deadline = self.mono() + remaining
                self.policy = p
            except (ValueError, KeyError, TypeError):
                atomic_json(self.path, self.policy)
                self.event('自动模式已过期或时钟异常，已关闭', 'auto_expired')

    def event(self, text, kind='info', detail=None):
        with self.lock:
            if kind in ('incoming','outgoing') and self.call_id and self.ring_call_id != self.call_id:
                self.ring_call_id = self.call_id
                self.call_started_mono = self.mono()
                self.call_ring_preferences = self.phone_preferences.capture_call()
                if kind == 'incoming':
                    self.gateway_audio.call(self.call_id,self.call_ring_preferences,self.call_started_mono)
            elif kind == 'call_ended':
                self.gateway_audio.end()
                self.ring_call_id = None
                self.call_started_mono = None
                self.call_ring_preferences = None
                self.phone_preferences.end_call()
            if kind == 'answered': self.gateway_audio.end()
            detail = dict(detail or {})
            if self.call_id:
                detail.setdefault('call_id', self.call_id)
                detail.setdefault('panel_id', self.panel_id)
            self.notice = text
            stamp, raw = self.wall(), json.dumps(detail or {}, ensure_ascii=False)
            row = self.db.execute('INSERT INTO events(time,kind,text,detail) VALUES(?,?,?,?)',
                                  (stamp, kind, text, raw))
            self.statistics.record(row.lastrowid, stamp, kind, raw)
            self.db.commit()

    def logs(self, before=None, limit=100, kind=None):
        limit = max(1, min(int(limit), 500))
        with self.lock:
            where, params = [], []
            if before is not None:
                where.append('id < ?')
                params.append(int(before))
            if kind:
                where.append('kind = ?')
                params.append(kind)
            sql = 'SELECT * FROM events'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY id DESC LIMIT ?'
            rows = [dict(r) for r in self.db.execute(sql, (*params, limit))]
            for row in rows:
                row['detail'] = json.loads(row['detail'])
            return rows

    def set_auto(self, minutes):
        if minutes is not None and (type(minutes) is not int or minutes not in DURATIONS):
            raise ValueError('Unsupported duration')
        with self.lock:
            policy = {'enabled': minutes is not None, 'minutes': minutes,
                      'expires_at': self.wall()+minutes*60 if minutes else None}
            atomic_json(self.path, policy)
            self.policy = policy
            self.deadline = self.mono()+minutes*60 if minutes else None
            label = '关闭' if minutes is None else ('无时限' if minutes == 0 else f'{minutes} 分钟')
            self.event('自动开门：'+label, 'auto_changed', policy)

    def control(self, action, panel=None, request_id=None, *, expected_call=None, phone=False, guard=None):
        if action not in ('preview', 'answer', 'open', 'hangup'):
            raise ValueError('Unknown action')
        if panel is not None and panel not in [p['id'] for p in self.config['panels']]:
            raise ValueError('Unknown panel')
        request_id = request_id or str(uuid.uuid4())
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 80:
            raise ValueError('Invalid request ID')
        with self.lock:
            signature = json.dumps([action, panel, expected_call]) if phone else json.dumps([action, panel])
            old = self.db.execute('SELECT action FROM requests WHERE id=?', (request_id,)).fetchone()
            if old:
                if old['action'] != signature:
                    raise ValueError('Request ID reused for another action')
                return {'request_id':request_id, 'duplicate':True}
            if phone and action != 'preview' and (not expected_call or expected_call != self.call_id):
                raise ValueError('会话已变化，请等待最新状态')
            if self.controller is None or self.network != 'ready':
                raise ValueError('门禁网络未就绪')
            if action == 'answer':
                raise ValueError('远程语音尚未启用；可查看视频、开门或挂断')
            if action == 'preview' and self.call != 'idle':
                raise ValueError('已有通话，请先挂断')
            if action == 'open' and (not self.allow_open or not self.relays or self.call not in ('early_video','audio')):
                raise ValueError('当前没有允许开门的会话')
            self.db.execute('INSERT INTO requests VALUES(?,?,?)', (request_id, signature, self.wall()))
            self.db.commit()
            try:
                if phone:
                    self.controller.enqueue(action, panel, request_id, expected_call, True, **({'guard': guard} if guard else {}))
                else:
                    self.controller.enqueue(action, panel, request_id)
            except Exception:
                self.db.execute('DELETE FROM requests WHERE id=?', (request_id,))
                self.db.commit()
                raise
            self.event('操作请求：'+{'preview':'查看视频','answer':'接听','open':'手动开门','hangup':'挂断'}[action], 'control_request', {'action':action,'panel':panel,'request_id':request_id})
        return {'request_id':request_id, 'duplicate':False}

    def tick(self):
        with self.lock:
            if self.deadline is not None and (self.mono() >= self.deadline or self.wall() >= self.policy['expires_at']):
                self.set_auto(None)
                self.event('自动开门已到期', 'auto_expired')

    def snapshot(self):
        with self.lock:
            self.tick()
            return {'mode':'live', 'network':self.network, 'call':self.call, 'panel':self.panel,
                    'call_id':self.call_id, 'panel_id':self.panel_id, 'direction':self.direction,
                    'identity':{k:self.config[k] for k in ('building','block','unit','extension')},
                    'panels':[{'id':p['id'],'name':p['name']} for p in self.config['panels']],
                    'auto':dict(self.policy), 'allow_open':self.allow_open, 'relays':list(self.relays),
                    'notice':self.notice, 'events':self.logs(limit=6),
                    'statistics':self.statistics.snapshot(self.wall()),
                    'time':self.wall(), 'local_time':datetime.fromtimestamp(self.wall()).isoformat(),
                    'utc_offset':datetime.fromtimestamp(self.wall()).astimezone().utcoffset().total_seconds(),
                    'clock':dict(self.clock_status), 'video_ready':self.video_jpeg is not None and self.mono()-self.video_updated < 5,
                    'ring_preferences':dict(self.call_ring_preferences) if self.call_id and self.call_ring_preferences else None,
                    'audio_available':False, 'phone_preferences':self.phone_preferences.snapshot(),
                    'call_age':max(0,self.mono()-self.call_started_mono) if self.call_id and self.call_started_mono is not None else 0}

    def phone_snapshot(self, panels):
        """Small, scoped projection. Never expose configuration or raw event detail."""
        with self.lock:
            full = self.snapshot()
            permitted = self.panel_id is None or self.panel_id in panels
            result = {k:full[k] for k in ('network', 'call', 'call_id', 'panel', 'panel_id',
                      'direction', 'auto', 'time', 'local_time', 'utc_offset', 'audio_available', 'phone_preferences', 'ring_preferences', 'call_age')}
            result['statistics'] = self.statistics.snapshot(self.wall(), panels)
            result['clock_synchronized'] = full['clock']['synchronized']
            result['panels'] = [p for p in full['panels'] if p['id'] in panels]
            result['video_ready'] = permitted and full['video_ready']
            result['allow_open'] = permitted and full['allow_open'] and bool(full['relays'])
            result['events'] = [
                {k:e[k] for k in ('id','time','kind')} | {k:e['detail'].get(k) for k in ('call_id','request_id')}
                for e in self.logs(limit=30)
                if e['kind'] in ('incoming','outgoing','call_ended','open_manual','open_auto',
                                 'open_unknown','open_denied','control_failed')
                and e['detail'].get('panel_id') in panels
            ][:3]
            if not permitted:
                result.update(call='busy', call_age=0, ring_preferences=None, call_id=None, panel=None, panel_id=None, direction=None)
            return result

    def stream_snapshot(self, panels):
        with self.lock:
            snapshot = self.phone_snapshot(panels)
            # Version describes global state, not a particular device's projection.
            full = self.snapshot()
            signature = json.dumps({k:v for k,v in full.items() if k not in ('time','local_time','call_age')}, sort_keys=True)
            if signature != self.stream_signature:
                self.stream_signature = signature
                self.stream_version += 1
            return {'schema':1, 'epoch':self.stream_epoch, 'version':self.stream_version,
                    'event_id':f'{self.stream_epoch}:{self.stream_version}',
                    'server_time':self.wall(), 'state':snapshot}
