import csv
import io
import json
import sqlite3
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .config import validate, load
from .state import atomic_json

WEB = Path(__file__).resolve().parent/'web'


def server(state, auth, address=('127.0.0.1', 8765)):

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
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def cookie(self):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get('Cookie', ''))
            except Exception:
                pass
            return cookie['fermax'].value if 'fermax' in cookie else ''

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
            static = {'/':'index.html','/app.js':'app.js','/style.css':'style.css','/settings.js':'settings.js'}
            if path in static:
                name = static[path]
                mime = {'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[name.split('.')[-1]]
                return self.send(200, (WEB/name).read_bytes(), mime)
            if path == '/health':
                return self.send(200, {'status':'ok', 'mode':'live'})
            if not self.authorized():
                return
            try:
                if path == '/v1/config':
                    saved = load(state.folder/'config.json')
                    self.send(200, {'config':saved, 'restart_required':saved != state.config})
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
            origin = self.headers.get('Origin')
            if origin and origin != 'http://'+self.headers.get('Host', ''):
                return self.send(403, {'error':'跨站请求被拒绝'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 8192:
                    raise ValueError('请求长度无效')
                self.connection.settimeout(5)
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('请求格式无效')
                if self.path in ('/v1/login','/v1/password') and auth.limited(self.client_address[0]):
                    return self.send(429, {'error':'Too many attempts; retry later'})
                if self.path == '/v1/login':
                    session = auth.login(data.get('password',''))
                    if not session:
                        return self.send(401, {'error':'Incorrect password'})
                    return self.send(200, {'ok':True}, extra={'Set-Cookie':f'fermax={session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400'})
                if not self.authorized():
                    return
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
            except (ValueError, TypeError, TimeoutError) as error:
                self.send(400, {'error':str(error)})

    result = ThreadingHTTPServer(address, Handler)
    result.daemon_threads = True
    return result
