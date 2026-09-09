"""Scoped, revocable integrations and a journal-backed event projection."""
import hashlib
import json
import secrets
import threading
import time
import uuid
from contextlib import contextmanager

from .state import atomic_json

VERSION = '0.7.0'
PERMISSIONS = {'state', 'events', 'camera', 'preview', 'hangup', 'open'}
KINDS = {'incoming', 'outgoing', 'call_ended', 'open_manual', 'open_auto',
         'open_unknown', 'open_denied', 'control_failed'}


class Integrations:
    def __init__(self, auth, state, clock=time.monotonic):
        self.auth, self.state, self.clock = auth, state, clock
        self.path = auth.folder/'integrations.json'
        self.pending = {}
        self.slots = threading.BoundedSemaphore(4)
        with state.lock:
            state.db.execute('CREATE TABLE IF NOT EXISTS integration_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            for key in ('gateway_id', 'journal_id'):
                state.db.execute('INSERT OR IGNORE INTO integration_meta VALUES(?,?)', (key, uuid.uuid4().hex))
            state.db.commit()
            self.identity = dict(state.db.execute('SELECT key,value FROM integration_meta'))

    @staticmethod
    def digest(token):
        if not isinstance(token, str) or len(token) > 256:
            return ''
        return hashlib.sha256(token.encode()).hexdigest()

    def read(self):
        self.auth.refresh()
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text())
        if not isinstance(data, dict):
            raise ValueError('Invalid integration store')
        if data.get('revision') != self.auth.record['revision']:
            return {}
        grants = data['integrations']
        if not isinstance(grants, dict):
            raise ValueError('Invalid integration store')
        return grants

    def save(self, grants):
        atomic_json(self.path, {'revision': self.auth.record['revision'], 'integrations': grants})

    def validate_scope(self, panels, permissions):
        configured = {p['id'] for p in self.state.config['panels']}
        if not isinstance(panels, list) or not panels or any(not isinstance(p, str) or p not in configured for p in panels):
            raise ValueError('请选择允许访问的门口机')
        if not isinstance(permissions, list) or any(not isinstance(p, str) or p not in PERMISSIONS for p in permissions):
            raise ValueError('集成权限无效')
        if not {'state', 'events'} <= set(permissions):
            raise ValueError('需要 state/events 权限')
        return list(dict.fromkeys(panels)), sorted(set(permissions))

    def pairing(self, name, panels, permissions):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
            raise ValueError('集成名称需为 1–60 个字符')
        with self.auth.lock:
            grants = self.read()
            panels, permissions = self.validate_scope(panels, permissions)
            now = self.clock()
            self.pending = {k: v for k, v in self.pending.items() if v['deadline'] > now and v['revision'] == self.auth.record['revision']}
            if len(grants) >= 32 or len(self.pending) >= 10:
                raise ValueError('集成或配对请求数量已达上限')
            code = secrets.token_urlsafe(18)
            self.pending[self.digest(code)] = {'name': name.strip(), 'panels': panels, 'permissions': permissions,
                                               'deadline': now+300, 'revision': self.auth.record['revision']}
            return {'code': code, 'expires_in': 300}

    @staticmethod
    def public(grant):
        return {k: grant[k] for k in ('id', 'name', 'panels', 'permissions', 'created_at')}

    def pair(self, code):
        with self.auth.lock:
            grants = self.read()
            digest = self.digest(code)
            pending = self.pending.get(digest)
            if not pending or pending['deadline'] <= self.clock() or pending['revision'] != self.auth.record['revision']:
                return None
            panels, permissions = self.validate_scope(pending['panels'], pending['permissions'])
            if len(grants) >= 32:
                raise ValueError('集成数量已达上限')
            token, identity = secrets.token_urlsafe(32), uuid.uuid4().hex
            grant = {'id': identity, 'name': pending['name'], 'panels': panels, 'permissions': permissions,
                     'created_at': self.state.wall(), 'digest': self.digest(token)}
            grants[identity] = grant
            self.save(grants)  # Do not consume or return credentials unless persistence succeeds.
            self.pending.pop(digest)
            return {'schema': 1, 'token': token, 'integration': self.public(grant), 'gateway': self.gateway()}

    def authorized(self, token):
        with self.auth.lock:
            digest = self.digest(token)
            for grant in self.read().values():
                if secrets.compare_digest(grant['digest'], digest):
                    self.validate_scope(grant['panels'], grant['permissions'])
                    return self.public(grant)
            return None

    def list(self):
        with self.auth.lock:
            return [self.public(g) for g in self.read().values()]

    def revoke(self, identity):
        if not isinstance(identity, str):
            raise ValueError('Invalid integration ID')
        with self.auth.lock:
            grants = self.read()
            grants.pop(identity, None)
            self.save(grants)
            # Cancel unconsumed pairing codes too; a revoke cannot be undone by an old code.
            self.pending.clear()

    def gateway(self):
        return {'id': self.identity['gateway_id'], 'version': VERSION}

    def head(self):
        return self.state.db.execute('SELECT COALESCE(MAX(id),0) FROM events').fetchone()[0]

    def cursor(self, identity):
        return f"{self.identity['journal_id']}:{identity}"

    def parse_cursor(self, cursor, head):
        try:
            journal, number = cursor.split(':')
            value = int(number)
            if journal != self.identity['journal_id'] or value < 0 or value > head:
                raise ValueError()
            return value
        except (AttributeError, TypeError, ValueError):
            return None

    def snapshot(self, grant):
        with self.state.lock:
            full = self.state.phone_snapshot(grant['panels'])
            fields = ('network', 'call', 'call_id', 'panel_id', 'panel', 'direction', 'panels', 'allow_open', 'video_ready', 'statistics', 'auto')
            projected = {k: full[k] for k in fields}
            projected['allow_open'] &= 'open' in grant['permissions']
            projected['video_ready'] &= 'camera' in grant['permissions']
            return {'schema': 1, 'gateway': self.gateway(), 'integration': grant, 'server_time': self.state.wall(),
                    'cursor': self.cursor(self.head()), 'state': projected}

    def batch(self, grant, after, until=None):
        with self.state.lock:
            head = self.head() if until is None else until
            rows = self.state.db.execute('SELECT id,time,kind,detail FROM events WHERE id>? AND id<=? ORDER BY id LIMIT 500', (after, head)).fetchall()
            events = []
            for row in rows:
                if row['kind'] not in KINDS:
                    continue
                detail = json.loads(row['detail'])
                if detail.get('panel_id') not in grant['panels']:
                    continue
                events.append({'id': self.cursor(row['id']), 'time': row['time'], 'kind': row['kind'],
                               **{k: detail.get(k) for k in ('panel_id', 'call_id', 'request_id')}})
            return events, rows[-1]['id'] if rows else head

    @contextmanager
    def guard(self, token, action, panel, call_id, expires_at, deadline, relay=None):
        # Caller holds state.lock; hold auth lock through actual dispatch so revoke
        # cannot interleave between the permission check and sending the command.
        with self.auth.lock:
            grant = self.authorized(token)
            if not grant or action not in grant['permissions'] or panel not in grant['panels']:
                raise ValueError('集成授权已撤销或操作未授权')
            now = self.state.wall()
            if not now <= expires_at <= now+30 or self.state.mono() > deadline:
                raise ValueError('操作请求已过期')
            if self.state.network != 'ready':
                raise ValueError('门禁网络未就绪')
            if action == 'preview':
                if self.state.call != 'idle':
                    raise ValueError('已有通话，预览已取消')
            elif not call_id or call_id != self.state.call_id or panel != self.state.panel_id:
                raise ValueError('会话已变化，操作已取消')
            if action == 'open' and (self.state.call not in ('early_video', 'audio') or not self.state.allow_open
                                     or not self.state.relays or (relay is not None and relay not in self.state.relays)):
                raise ValueError('门口机已不再允许此次开门')
            yield
