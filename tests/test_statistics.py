"""Daily facts from synthetic events only; no controller/network/audio hardware."""
import json
import os
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime
from unittest.mock import patch
from fermax.state import State
from fermax.statistics import Statistics


class DailyStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = datetime(2030, 5, 18, 12).timestamp()
        self.states = []
        self.addCleanup(lambda: [s.db.close() for s in self.states])
        self.s = self.make()

    def make(self):
        state = State(self.temp.name, wall=lambda: self.now)
        self.states.append(state)
        return state

    def event(self, kind, **detail):
        self.s.event('Synthetic activity', kind, detail)

    def stats(self, panels=None):
        return self.s.statistics.snapshot(self.now, panels)

    def test_unique_calls_and_confirmations_not_preview_or_requests(self):
        for _ in range(3):
            self.event('incoming', call_id='call-a', panel_id='lobby')
            self.event('open_manual', request_id='one', call_id='call-a', panel_id='lobby')
            self.event('open_auto', call_id='call-a', panel_id='lobby')
        self.event('open_manual', request_id='two', call_id='call-a', panel_id='lobby')
        for kind in ['outgoing','open_denied','open_unknown','control_request','answered']:
            self.event(kind, call_id='call-b', panel_id='lobby')
        self.assertEqual((self.stats()['incoming'],self.stats()['openings']), (1,3))
        self.assertEqual(self.make().snapshot()['statistics'], self.s.snapshot()['statistics'])

    def test_scope_and_unknown_legacy_panel(self):
        self.event('incoming',call_id='allowed',panel_id='lobby')
        self.event('incoming',call_id='private',panel_id='side')
        self.event('incoming')
        self.assertEqual(self.stats()['incoming'],3)
        self.assertEqual(self.s.phone_snapshot(['lobby'])['statistics']['incoming'],1)
        self.assertEqual(self.stats([])['incoming'],0)
        self.assertNotIn('private',json.dumps(self.s.phone_snapshot(['lobby'])['statistics']))

    def test_midnight_first_event_and_restart(self):
        self.now=datetime(2030,5,18,23,59,59).timestamp()
        self.event('incoming',call_id='same',panel_id='lobby')
        old=self.s.stream_snapshot(['lobby'])
        self.now=datetime(2030,5,19,0,0,0).timestamp()
        self.event('incoming',call_id='same',panel_id='lobby')
        self.event('open_auto',call_id='same',panel_id='lobby')
        self.assertEqual(self.stats()['incoming'],0)
        self.assertEqual(self.stats()['openings'],1)
        self.assertGreater(self.s.stream_snapshot(['lobby'])['version'],old['version'])
        self.assertEqual(self.make().snapshot()['statistics']['incoming'],0)

    def test_midnight_without_event_and_clock_rollback(self):
        self.event('incoming',call_id='a')
        self.now=datetime(2030,5,19,0,0,0).timestamp()
        self.assertEqual(self.stats()['incoming'],0)
        self.now=datetime(2030,5,18,13).timestamp()
        self.assertEqual(self.stats()['incoming'],1)

    def test_migration_old_data_and_rollback_writes(self):
        self.event('incoming',call_id='a',panel_id='lobby')
        self.s.db.execute('DROP TABLE activity_facts')
        self.s.db.execute('DROP TABLE activity_cursor')
        for raw in ['{}','{}','{}','{}']:
            self.s.db.execute('INSERT INTO events(time,kind,text,detail) VALUES(?,?,?,?)',(self.now,'incoming','legacy',raw))
        self.s.db.commit()
        restored=self.make()
        self.assertEqual(restored.statistics.snapshot(self.now)['incoming'],5)
        self.assertEqual(restored.statistics.snapshot(self.now,['lobby'])['incoming'],1)
        # Simulate the older release adding a journal row without the new projection.
        restored.db.execute('INSERT INTO events(time,kind,text,detail) VALUES(?,?,?,?)',(self.now,'open_manual','legacy','{}'))
        restored.db.commit()
        self.assertEqual(self.make().statistics.snapshot(self.now)['openings'],1)

    def test_optional_write_failure_preserves_journal_and_recovers_on_restart(self):
        with patch.object(self.s.statistics,'insert',side_effect=sqlite3.OperationalError('synthetic full')):
            self.event('incoming',call_id='a')
        self.assertFalse(self.stats()['available'])
        self.assertIsNone(self.stats()['incoming'])
        self.assertEqual(self.s.logs()[0]['kind'],'incoming')
        self.assertEqual(self.make().snapshot()['statistics']['incoming'],1)

    def test_optional_query_and_migration_failure_are_unavailable(self):
        self.s.db.execute('DROP TABLE activity_facts')
        self.assertFalse(self.stats()['available'])
        with patch.object(Statistics,'insert',side_effect=sqlite3.OperationalError('synthetic')):
            self.s.db.execute('DELETE FROM activity_cursor')
            self.event('incoming',call_id='a')
            restored=self.make()
            self.assertFalse(restored.snapshot()['statistics']['available'])
            restored.event('still journaling')
            self.assertEqual(restored.logs()[0]['text'],'still journaling')

    def test_malformed_history_is_unavailable_not_a_guessed_count(self):
        self.s.db.execute('INSERT INTO events(time,kind,text,detail) VALUES(?,?,?,?)',(self.now,'incoming','legacy','null'))
        self.s.db.commit()
        self.assertFalse(self.make().statistics.snapshot(self.now)['available'])

    def test_cursor_failure_rolls_back_fact_not_journal(self):
        self.s.db.execute("CREATE TRIGGER synthetic_cursor_failure BEFORE UPDATE ON activity_cursor BEGIN SELECT RAISE(ABORT,'synthetic'); END;")
        self.event('incoming',call_id='a',panel_id='lobby')
        self.assertEqual(self.s.logs()[0]['kind'],'incoming')
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM activity_facts').fetchone()[0],0)
        self.assertFalse(self.stats()['available'])
        self.s.db.execute('DROP TRIGGER synthetic_cursor_failure')
        self.s.db.commit()
        self.assertEqual(self.make().statistics.snapshot(self.now)['incoming'],1)

    def test_daily_query_cache_avoids_repeated_scans(self):
        self.event('incoming',call_id='a')
        statements=[]
        self.s.db.set_trace_callback(statements.append)
        for _ in range(20):
            self.s.stream_snapshot(['lobby'])
        self.assertEqual(sum('COUNT(*)' in sql for sql in statements),1)

    @unittest.skipUnless(hasattr(time,'tzset'), 'POSIX timezone test')
    def test_dst_days_use_local_midnights(self):
        old=os.environ.get('TZ')
        try:
            os.environ['TZ']='America/New_York';time.tzset()
            for month,day,hours in [(3,10,23),(11,3,25)]:
                # 2030 US transition dates.
                self.now=datetime(2030,month,day,0).timestamp()
                start=self.now
                self.event('incoming',call_id=f'{month}-start')
                self.now=start+hours*3600-1
                self.event('incoming',call_id=f'{month}-end')
                self.assertEqual(self.stats()['incoming'],2)
                self.now+=1
                self.assertEqual(self.stats()['incoming'],0)
        finally:
            if old is None: os.environ.pop('TZ',None)
            else: os.environ['TZ']=old
            time.tzset()
