"""Revocable device grants and short-lived, renewable phone-only sessions."""
import hashlib
import json
import secrets
import time

from .state import atomic_json


class Devices:
    def __init__(self, auth, clock=time.monotonic):
        self.auth, self.clock = auth, clock
        self.path = auth.folder/'phone-devices.json'
        self.sessions = {}

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def read(self):
        self.auth.refresh()
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text())
        if data.get('revision') != self.auth.record['revision']:
            self.sessions.clear()
            return {}
        return data['devices']

    def save(self, devices):
        atomic_json(self.path, {'revision':self.auth.record['revision'], 'devices':devices})

    def enroll(self, name, panels):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
            raise ValueError('设备名称需为 1–60 个字符')
        with self.auth.lock:
            devices = self.read()
            if len(devices) >= 32:
                raise ValueError('设备数量已达上限，请先撤销旧设备')
            token, identity = secrets.token_urlsafe(32), secrets.token_hex(16)
            devices[identity] = {'id':identity, 'name':name.strip(), 'panels':list(panels),
                                 'digest':self.digest(token), 'created_at':time.time()}
            self.save(devices)
            return token

    def renew(self, grant):
        with self.auth.lock:
            devices = self.read()
            digest = self.digest(grant)
            device = next((v for v in devices.values() if secrets.compare_digest(v['digest'], digest)), None)
            if not device:
                return None
            now = self.clock()
            self.sessions = {k:v for k,v in self.sessions.items() if v[1] > now}
            if len(self.sessions) >= 256:
                del self.sessions[next(iter(self.sessions))]
            token = secrets.token_urlsafe(32)
            self.sessions[self.digest(token)] = (device['id'], now+300)
            return token, {k:v for k,v in device.items() if k != 'digest'}

    def authorized(self, token):
        with self.auth.lock:
            devices = self.read()
            session = self.sessions.get(self.digest(token))
            if not session or session[1] <= self.clock():
                return None
            device = devices.get(session[0])
            return {k:v for k,v in device.items() if k != 'digest'} if device else None

    def list(self):
        with self.auth.lock:
            return [{k:v for k,v in d.items() if k != 'digest'} for d in self.read().values()]

    def revoke(self, identity):
        with self.auth.lock:
            devices = self.read()
            devices.pop(identity, None)
            self.save(devices)
            self.sessions = {k:v for k,v in self.sessions.items() if v[0] != identity}

    def revoke_grant(self, grant):
        with self.auth.lock:
            digest = self.digest(grant)
            for identity, device in self.read().items():
                if secrets.compare_digest(device['digest'], digest):
                    self.revoke(identity)
                    break
