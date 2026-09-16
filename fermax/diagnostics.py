"""Bounded local diagnostics, separate from the permanent visitor journal.

Callers supply metadata only: never packets, credentials, SDP or media.
An independent lock avoids the state/audio lock inversion.
"""
import json
import logging
import sqlite3
import threading
import time
from contextlib import closing


class Diagnostics:
    LIMIT = 10000
    AGE = 7 * 86400

    def __init__(self, folder, wall=time.time):
        self.wall = wall
        self.lock = threading.RLock()
        self.path = folder/'diagnostics.sqlite3'
        self.available = True
        self.warned = False
        try:
            with closing(sqlite3.connect(self.path, timeout=.1)) as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('CREATE TABLE IF NOT EXISTS diagnostics(id INTEGER PRIMARY KEY AUTOINCREMENT,time REAL,kind TEXT,detail TEXT)')
                db.commit()
        except sqlite3.Error:
            self.available = False
            logging.warning('Diagnostic database unavailable; call processing remains enabled')
        self.limits = {}

    def record(self, kind, detail=None, *, rate_key=None, interval=1):
        if not self.available: return False
        try:
            with self.lock:
                now = self.wall()
                if rate_key:
                    if now-self.limits.get(rate_key, float('-inf')) < interval:
                        return False
                    self.limits = {k:v for k,v in self.limits.items() if now-v < 3600}
                    self.limits[rate_key] = now
                raw = json.dumps(detail or {}, ensure_ascii=False)
                if len(raw) > 4096:
                    return False
                with closing(sqlite3.connect(self.path, timeout=.1)) as db:
                    db.execute('INSERT INTO diagnostics(time,kind,detail) VALUES(?,?,?)', (now,kind,raw))
                    db.execute('DELETE FROM diagnostics WHERE time < ? OR id <= (SELECT COALESCE(MAX(id),0)-? FROM diagnostics)', (now-self.AGE,self.LIMIT))
                    db.commit()
                return True
        except (sqlite3.Error, ValueError, TypeError):
            if not self.warned:
                self.warned = True
                logging.warning('Diagnostic record unavailable')
            return False

    def logs(self, before=None, limit=100):
        if not self.available: return []
        with self.lock, closing(sqlite3.connect(self.path, timeout=.1)) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute('SELECT * FROM diagnostics WHERE time >= ? AND id < ? ORDER BY id DESC LIMIT ?',
                (self.wall()-self.AGE, int(before) if before is not None else 2**63-1,max(1,min(500,int(limit)))))
            return [dict(r) | {'detail':json.loads(r['detail'])} for r in rows]
