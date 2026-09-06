"""Single-user password hashes, revocable sessions and separate API credentials."""
import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path
from .state import atomic_json

ITERATIONS = 600000


def password_record(password):
    if not isinstance(password,str) or not 12 <= len(password) <= 128:
        raise ValueError('密码长度需为 12–128 个字符')
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256',password.encode(),salt,ITERATIONS)
    return {'algorithm':'pbkdf2-sha256','iterations':ITERATIONS,'salt':salt.hex(),
            'hash':digest.hex(),'revision':secrets.token_hex(16)}


def set_password(folder,password):
    atomic_json(Path(folder)/'auth.json',password_record(password))


class Auth:
    def __init__(self,folder):
        self.folder = Path(folder)
        self.lock = threading.RLock()
        self.sessions = {}
        self.record = None
        self.attempts = {}
        self.refresh()

    def refresh(self):
        record = json.loads((self.folder/'auth.json').read_text())
        if record.get('algorithm') != 'pbkdf2-sha256' or not 100000 <= record.get('iterations',0) <= 2000000:
            raise ValueError('密码配置无效，请用管理命令重置')
        if self.record != record:
            self.sessions.clear()
            self.record = record

    def verify(self,password):
        with self.lock:
            self.refresh()
            if not isinstance(password,str) or len(password)>128:
                return False
            r = self.record
            digest = hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(r['salt']),r['iterations'])
            return hmac.compare_digest(digest.hex(),r['hash'])

    def limited(self,address):
        with self.lock:
            now = time.monotonic()
            self.attempts = {k:[t for t in v if t>now-60] for k,v in self.attempts.items() if v and v[-1]>now-60}
            attempts = self.attempts.setdefault(address,[])
            if len(attempts)>=10 or len(self.attempts)>1024:
                return True
            attempts.append(now)
            return False

    def login(self,password):
        with self.lock:
            if not self.verify(password):
                return None
            now = time.monotonic()
            self.sessions = {k:v for k,v in self.sessions.items() if v>now}
            if len(self.sessions)>=128:
                del self.sessions[next(iter(self.sessions))]
            token = secrets.token_urlsafe(32)
            self.sessions[token] = now+86400
            return token

    def authorized(self,bearer,cookie):
        with self.lock:
            self.refresh()
            if bearer:
                path = self.folder/'api-token'
                return path.exists() and hmac.compare_digest(bearer.encode(),path.read_text().strip().encode())
            return self.sessions.get(cookie,0)>time.monotonic()

    def change(self,current,new):
        with self.lock:
            if not self.verify(current):
                raise ValueError('当前密码不正确')
            set_password(self.folder,new)
            self.refresh()

    def logout(self,cookie):
        with self.lock:
            self.sessions.pop(cookie,None)
