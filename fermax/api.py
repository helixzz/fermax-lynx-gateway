import csv
import io
import json
import sqlite3
import time
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .config import validate, load
from .state import atomic_json
from .phone import Devices

WEB = Path(__file__).resolve().parent/'web'


def server(state, auth, address=('127.0.0.1', 8765)):
    # Loopback and LAN listeners share grants, short sessions and stream limits.
    with auth.lock:
        if not hasattr(auth, 'devices'):
            auth.devices = Devices(auth)
    devices = auth.devices

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_):
            pass

        def send(self, code, body, mime='application/json; charset=utf-8', extra=None):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob: data:; frame-ancestors 'none'")
            for key, value in (extra or {}).items():
                for item in value if isinstance(value, list) else [value]:
                    self.send_header(key, item)
            self.end_headers()
            self.wfile.write(data)

        def cookie(self, name='fermax'):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get('Cookie', ''))
            except Exception:
                pass
            return cookie[name].value if name in cookie else ''

        def same_origin(self):
            origin = self.headers.get('Origin')
            return not origin or origin == 'http://'+self.headers.get('Host', '')

        def phone_device(self):
            try:
                device = devices.authorized(self.cookie('fermax_phone'))
            except (ValueError, OSError, KeyError, TypeError):
                self.send(503, {'error':'设备授权暂不可用'})
                return None
            if not device:
                self.send(401, {'error':'请重新授权话机设备'})
            return device

        @staticmethod
        def phone_cookies(grant=None, session=None, clear=False):
            result = []
            for name, token, path, age in (
                ('fermax_device', grant, '/v1/phone/session', 34560000),
                ('fermax_phone', session, '/v1/phone', 300),
            ):
                if token is not None or clear:
                    result.append(f'{name}={token or ""}; HttpOnly; SameSite=Strict; Path={path}; Max-Age={0 if clear else age}')
            return result

        def phone_stream(self, device):
            if not state.stream_slots.acquire(blocking=False):
                return self.send(503, {'error':'状态连接数量已达上限'}, extra={'Retry-After':'5'})
            try:
                self.connection.settimeout(2)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Accel-Buffering', 'no')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.close_connection = True
                previous, last_send = None, 0
                while not result.stopping.is_set():
                    # Revocation also closes existing streams; never trust admission alone.
                    try:
                        current = devices.authorized(self.cookie('fermax_phone'))
                    except (ValueError, OSError, KeyError, TypeError):
                        current = None
                    if not current:
                        self.wfile.write(b'event: unauthorized\ndata: {}\n\n')
                        self.wfile.flush()
                        return
                    body = state.stream_snapshot(current['panels'])
                    cursor = body['event_id']
                    now = time.monotonic()
                    if cursor != previous or now-last_send >= 15:
                        # Every data message is a complete snapshot: gaps/restarts never
                        # replay controls, and a slow client cannot grow an event queue.
                        kind = 'snapshot' if cursor != previous else 'heartbeat'
                        data = json.dumps(body, ensure_ascii=False, separators=(',',':'))
                        self.wfile.write(f'id: {cursor}\nevent: {kind}\ndata: {data}\n\n'.encode())
                        self.wfile.flush()
                        previous, last_send = cursor, now
                    result.stopping.wait(0.5)
            except (OSError, TimeoutError):
                pass
            finally:
                state.stream_slots.release()

        def phone_get(self, path):
            if not self.same_origin():
                return self.send(403, {'error':'跨站请求被拒绝'})
            device = self.phone_device()
            if not device:
                return
            if path == '/v1/phone/state':
                return self.send(200, state.stream_snapshot(device['panels']))
            if path == '/v1/phone/events':
                return self.phone_stream(device)
            if path == '/v1/phone/frame.jpg':
                with state.lock:
                    allowed = state.panel_id in device['panels']
                    image = state.video_jpeg
                    fresh = state.mono()-state.video_updated < 5
                if allowed and image and fresh:
                    return self.send(200, image, 'image/jpeg')
                return self.send(404, {'error':'暂无视频帧'})
            return self.send(404, {'error':'Not found'})

        def authorized(self):
            header = self.headers.get('Authorization', '')
            bearer = header[7:] if header.startswith('Bearer ') else ''
            try:
                allowed = auth.authorized(bearer, self.cookie())
            except (ValueError, OSError, KeyError):
                self.send(503, {'error':'Authentication unavailable; reset credentials on server'})
                return False
            if not allowed:
                self.send(401, {'error':'Please log in'})
            return allowed

        def do_GET(self):
            path = urlsplit(self.path).path
            static = {'/':'index.html','/app.js':'app.js','/style.css':'style.css','/settings.js':'settings.js',
                      '/phone':'phone.html','/phone.js':'phone.js','/phone.css':'phone.css'}
            if path in static:
                name = static[path]
                mime = {'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[name.split('.')[-1]]
                return self.send(200, (WEB/name).read_bytes(), mime)
            if path == '/health':
                return self.send(200, {'status':'ok', 'mode':'live'})
            if path.startswith('/v1/phone/'):
                return self.phone_get(path)
            if not self.authorized():
                return
            try:
                if path == '/v1/config':
                    saved = load(state.folder/'config.json')
                    self.send(200, {'config':saved, 'restart_required':saved != state.config})
                elif path == '/v1/devices':
                    self.send(200, {'devices':devices.list()})
                elif path == '/v1/state':
                    self.send(200, state.snapshot())
                elif path == '/v1/frame.jpg':
                    with state.lock:
                        image = state.video_jpeg
                        fresh = state.mono()-state.video_updated < 5
                    self.send(200, image, 'image/jpeg') if image and fresh else self.send(404, {'error':'暂无视频帧'})
                elif path == '/v1/logs':
                    args = parse_qs(urlsplit(self.path).query)
                    rows = state.logs(args.get('before',[None])[0], args.get('limit',[100])[0], args.get('kind',[None])[0])
                    self.send(200, {'events':rows,'next_before':rows[-1]['id'] if rows else None})
                elif path == '/v1/logs/export':
                    # Stream a consistent SQLite read snapshot, no retention cap.
                    db = sqlite3.connect(state.folder/'events.sqlite3')
                    try:
                        cursor = db.execute('SELECT id,time,kind,text,detail FROM events ORDER BY id')
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/csv; charset=utf-8')
                        self.send_header('Content-Disposition', 'attachment; filename="fermax-events.csv"')
                        self.send_header('Cache-Control','no-store')
                        self.end_headers()
                        self.wfile.write(b'\xef\xbb\xbf')
                        self.wfile.write(b'id,time,kind,text,detail\r\n')
                        for row in cursor:
                            out = io.StringIO()
                            csv.writer(out).writerow([("'"+v if isinstance(v,str) and v and v[:1] in '=+-@' else v) for v in row])
                            self.wfile.write(out.getvalue().encode())
                    finally:
                        db.close()
                else:
                    self.send(404, {'error':'Not found'})
            except (ValueError, TypeError):
                self.send(400, {'error':'查询参数无效'})
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            if not self.same_origin():
                return self.send(403, {'error':'跨站请求被拒绝'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 8192:
                    raise ValueError('请求长度无效')
                self.connection.settimeout(5)
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('请求格式无效')
                if self.path in ('/v1/login','/v1/password','/v1/phone/enroll','/v1/devices/revoke') and auth.limited(self.client_address[0]):
                    return self.send(429, {'error':'Too many attempts; retry later'})
                if self.path == '/v1/login':
                    session = auth.login(data.get('password',''))
                    if not session:
                        return self.send(401, {'error':'Incorrect password'})
                    return self.send(200, {'ok':True}, extra={'Set-Cookie':f'fermax={session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400'})
                if self.path == '/v1/phone/session':
                    grant = self.cookie('fermax_device')
                    renewed = devices.renew(grant)
                    if not renewed:
                        return self.send(401, {'error':'请重新授权话机设备'})
                    session, device = renewed
                    return self.send(200, {'device':device}, extra={'Set-Cookie':self.phone_cookies(grant,session)})
                if self.path == '/v1/phone/session/logout':
                    devices.revoke_grant(self.cookie('fermax_device'))
                    return self.send(200, {'ok':True}, extra={'Set-Cookie':self.phone_cookies(clear=True)})
                if self.path == '/v1/phone/control':
                    device = self.phone_device()
                    if not device:
                        return
                    with state.lock:
                        action, panel = data.get('action'), data.get('panel')
                        if action == 'preview':
                            if panel not in device['panels']:
                                raise PermissionError('门口机未授权')
                        elif state.panel_id is None:
                            raise ValueError('当前没有可用会话，请等待最新状态')
                        elif state.panel_id not in device['panels']:
                            raise PermissionError('当前会话未授权')
                        if not data.get('request_id'):
                            raise ValueError('缺少 request_id')
                        response = state.control(action, panel, data['request_id'],
                                                 expected_call=data.get('call_id'), phone=True)
                    return self.send(202, response)
                if not self.authorized():
                    return
                if self.path == '/v1/phone/enroll':
                    if not auth.verify(data.get('password')):
                        return self.send(401, {'error':'管理员密码不正确'})
                    panels = data.get('panels')
                    valid = {p['id'] for p in state.config['panels']}
                    if not isinstance(panels,list) or not panels or any(not isinstance(p,str) or p not in valid for p in panels):
                        raise ValueError('请选择允许控制的门口机')
                    grant = devices.enroll(data.get('name'), list(dict.fromkeys(panels)))
                    # Entering phone mode does not leave an administrator session behind.
                    auth.logout(self.cookie())
                    cookies = self.phone_cookies(grant)
                    cookies.append('fermax=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
                    return self.send(200, {'ok':True}, extra={'Set-Cookie':cookies})
                if self.path == '/v1/devices/revoke':
                    if not auth.verify(data.get('password')):
                        return self.send(401, {'error':'管理员密码不正确'})
                    devices.revoke(data.get('id'))
                    return self.send(200, {'ok':True})
                if self.path == '/v1/logout':
                    auth.logout(self.cookie())
                    return self.send(200, {'ok':True}, extra={'Set-Cookie':'fermax=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
                if self.path == '/v1/password':
                    auth.change(data.get('current_password'), data.get('new_password'))
                    state.event('Web password changed; sessions revoked', 'password_changed')
                    return self.send(200, {'ok':True}, extra={'Set-Cookie':'fermax=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
                if self.path == '/v1/config':
                    with state.lock:
                        if state.call != 'idle':
                            raise ValueError('End the call before changing device configuration')
                        atomic_json(state.folder/'config.json',validate(data))
                        state.event('Device configuration saved; restart required', 'config_changed')
                    return self.send(200, {'ok':True,'restart_required':data != state.config})
                if self.path == '/v1/auto':
                    if 'minutes' not in data:
                        raise ValueError('缺少 minutes')
                    state.set_auto(data['minutes'])
                elif self.path == '/v1/control':
                    return self.send(202, state.control(data.get('action'), data.get('panel'), data.get('request_id')))
                else:
                    return self.send(404, {'error':'Not found'})
                self.send(200, state.snapshot())
            except PermissionError as error:
                self.send(403, {'error':str(error)})
            except (ValueError, TypeError, TimeoutError) as error:
                self.send(400, {'error':str(error)})

    class PhoneServer(ThreadingHTTPServer):
        def shutdown(self):
            self.stopping.set()
            super().shutdown()

    result = PhoneServer(address, Handler)
    result.stopping = threading.Event()
    result.daemon_threads = True
    return result
