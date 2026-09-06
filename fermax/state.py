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
        self.path = self.folder/'policy.json'
        self.db = sqlite3.connect(self.folder/'events.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, time REAL NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, detail TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, action TEXT NOT NULL, time REAL NOT NULL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS events_kind_id ON events(kind,id)')
        self.db.commit()
        self.policy = {'enabled': False, 'minutes': None, 'expires_at': None}
        self.deadline = None
        self.call, self.panel, self.relays = 'idle', None, []
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
            self.notice = text
            self.db.execute('INSERT INTO events(time,kind,text,detail) VALUES(?,?,?,?)',
                            (self.wall(), kind, text, json.dumps(detail or {}, ensure_ascii=False)))
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

    def control(self, action, panel=None, request_id=None):
        if action not in ('preview', 'answer', 'open', 'hangup'):
            raise ValueError('Unknown action')
        if panel is not None and panel not in [p['id'] for p in self.config['panels']]:
            raise ValueError('Unknown panel')
        request_id = request_id or str(uuid.uuid4())
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 80:
            raise ValueError('Invalid request ID')
        with self.lock:
            signature = json.dumps([action, panel])
            old = self.db.execute('SELECT action FROM requests WHERE id=?', (request_id,)).fetchone()
            if old:
                if old['action'] != signature:
                    raise ValueError('Request ID reused for another action')
                return {'request_id':request_id, 'duplicate':True}
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
                    'identity':{k:self.config[k] for k in ('building','block','unit','extension')},
                    'panels':[{'id':p['id'],'name':p['name']} for p in self.config['panels']],
                    'auto':dict(self.policy), 'allow_open':self.allow_open, 'relays':list(self.relays),
                    'notice':self.notice, 'events':self.logs(limit=6),
                    'time':self.wall(), 'local_time':datetime.fromtimestamp(self.wall()).isoformat(),
                    'clock':dict(self.clock_status), 'video_ready':self.video_jpeg is not None and self.mono()-self.video_updated < 5,
                    'audio_available':False}
