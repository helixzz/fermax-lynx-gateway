"""Derived, rebuildable daily activity facts; never a source of door control."""
import json
from contextlib import contextmanager
import sqlite3
from datetime import datetime, time, timedelta


class Statistics:
    KINDS = {'incoming': 'incoming', 'open_manual': 'openings', 'open_auto': 'openings'}

    def __init__(self, db):
        self.db = db
        self.available = False
        self.cache = None
        # A savepoint isolates only the optional projection, not the event journal.
        try:
            with self.savepoint():
                db.execute('CREATE TABLE IF NOT EXISTS activity_facts(metric TEXT NOT NULL, event_key TEXT NOT NULL, time REAL NOT NULL, panel_id TEXT, PRIMARY KEY(metric,event_key))')
                db.execute('CREATE INDEX IF NOT EXISTS activity_time ON activity_facts(time,panel_id)')
                db.execute('CREATE TABLE IF NOT EXISTS activity_cursor(id INTEGER PRIMARY KEY CHECK(id=1), event_id INTEGER NOT NULL)')
                row = db.execute('SELECT event_id FROM activity_cursor WHERE id=1').fetchone()
                cursor = row[0] if row else 0
                for event in db.execute('SELECT id,time,kind,detail FROM events WHERE id>? ORDER BY id', (cursor,)):
                    self.insert(*event)
                last = db.execute('SELECT COALESCE(MAX(id),0) FROM events').fetchone()[0]
                db.execute('INSERT OR REPLACE INTO activity_cursor VALUES(1,?)', (last,))
            self.available = True
        except (sqlite3.Error, ValueError, TypeError):
            pass

    @contextmanager
    def savepoint(self):
        self.db.execute('SAVEPOINT activity_projection')
        try:
            yield
            self.db.execute('RELEASE activity_projection')
        except Exception:
            self.db.execute('ROLLBACK TO activity_projection')
            self.db.execute('RELEASE activity_projection')
            raise

    def insert(self, event_id, stamp, kind, raw):
        if kind not in self.KINDS:
            return
        detail = json.loads(raw)
        if not isinstance(detail, dict):
            raise ValueError('Invalid historical activity detail')
        field = 'request_id' if kind == 'open_manual' else 'call_id'
        value = detail.get(field)
        key = kind+':'+value if isinstance(value, str) and value else 'legacy:'+str(event_id)
        panel = detail.get('panel_id')
        panel = panel if isinstance(panel, str) and panel else None
        self.db.execute('INSERT OR IGNORE INTO activity_facts VALUES(?,?,?,?)',
                        (self.KINDS[kind], key, stamp, panel))

    def record(self, event_id, stamp, kind, raw):
        if not self.available:
            return
        try:
            with self.savepoint():
                self.insert(event_id, stamp, kind, raw)
                self.db.execute('UPDATE activity_cursor SET event_id=? WHERE id=1', (event_id,))
            self.cache = None
        except (sqlite3.Error, ValueError, TypeError):
            self.available = False
            self.cache = None

    def snapshot(self, now, panels=None):
        day = datetime.fromtimestamp(now).date()
        start = datetime.combine(day, time()).timestamp()
        end = datetime.combine(day+timedelta(days=1), time()).timestamp()
        result = {'date': day.isoformat(), 'available': False, 'incoming': None, 'openings': None}
        if not self.available:
            return result
        try:
            # Cache all panel groups once; scoped callers never receive other groups.
            key = (start, end)
            if self.cache is None or self.cache[0] != key:
                rows = list(self.db.execute('SELECT metric,panel_id,COUNT(*) FROM activity_facts WHERE time>=? AND time<? GROUP BY metric,panel_id', key))
                self.cache = (key, rows)
            result.update(available=True, incoming=0, openings=0)
            for metric, panel, count in self.cache[1]:
                if panels is None or panel in panels:
                    result[metric] += count
        except sqlite3.Error:
            self.available = False
            result.update(available=False, incoming=None, openings=None)
        return result
