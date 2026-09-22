import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fermax.control_trace import CallTrace, semantics
from fermax.diagnostics import Diagnostics


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 10.0
        self.state = SimpleNamespace(call_id='synthetic-call', panel_id='panel',
            diagnostics=Diagnostics(Path(self.temp.name), wall=lambda: self.now))
        self.trace = CallTrace(self.state, clock=lambda: self.now)

    def test_allowlist_hides_labels_credentials_and_caps_size(self):
        fields = {'relayTags':['private-label']*100, 'relayName':'private-label',
            'doormatic':True, 'pmuTag':'private-pmu', 'password':'secret', 'state':False,
            'allowOpenDoor':'not-a-boolean', 'result':'untrusted-response'}
        safe = semantics(fields)
        self.assertEqual(safe['relay_count'],100)
        self.assertEqual(len(safe['relay_fingerprints']),16)
        self.assertEqual(safe['relay_fingerprint'],safe['relay_fingerprints'][0])
        self.assertTrue(safe['relays_truncated'])
        self.assertNotIn('allowOpenDoor',safe)
        for raw in ('private-label','private-pmu','secret','untrusted-response'):
            self.assertNotIn(raw,json.dumps(safe))

    def test_keepalive_aggregates_but_forces_failure_and_open_snapshot(self):
        p=SimpleNamespace(error=None,result={'state':True})
        for _ in range(5):
            self.trace.sent+=1
            self.trace.keep_result(p)
            self.now+=1
        self.assertEqual(len(self.state.diagnostics.logs()),1)
        self.trace.summary('before_open',force=True)
        row=self.state.diagnostics.logs()[0]['detail']
        self.assertEqual((row['sent'],row['ok'],row['last_ok_age_ms']),(5,5,1000))
        self.trace.keep_result(SimpleNamespace(error='timeout',result=None))
        self.assertEqual(self.state.diagnostics.logs()[0]['detail']['failed'],1)

    def test_false_keepalive_is_failure_and_new_call_resets_counters(self):
        self.trace.keep_result(SimpleNamespace(error=None,result={'state':False}))
        self.assertEqual(self.trace.failed,1)
        fresh=CallTrace(self.state)
        self.assertEqual((fresh.sent,fresh.failed,fresh.last_ok),(0,0,None))

    def test_capability_only_logs_changes_and_no_unknown_fields(self):
        self.trace.capability({'openDoorEnable':True,'password':'secret'},True)
        self.trace.capability({'openDoorEnable':True},True)
        self.trace.capability({'openDoorEnable':False},False)
        self.assertEqual(len(self.state.diagnostics.logs()),2)
        self.assertNotIn('secret',json.dumps(self.state.diagnostics.logs()))

    def test_unavailable_store_does_not_break_trace(self):
        self.state.diagnostics.available=False
        self.trace.keep_result(SimpleNamespace(error=None,result={'state':True}))
        self.trace.summary('ended',force=True)
        self.trace.capability({'openDoorEnable':False},False)
        self.assertEqual(self.trace.ok,1)

    def test_invalid_transport_events_rate_limited(self):
        for _ in range(50):
            self.trace.record('session_transport', {'stage':'invalid','port':1234})
        self.assertEqual(len(self.state.diagnostics.logs()),1)
