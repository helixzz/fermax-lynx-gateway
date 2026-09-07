"""Exercise the live orchestrator without creating sockets or sending commands."""
import collections
import queue
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

try:
    from fermax.controller import Controller
except ModuleNotFoundError as error:
    if error.name != 'enet':
        raise
    Controller = None
from fermax.state import State


@unittest.skipIf(Controller is None, 'python3-enet required to import controller')
class ControllerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.state = State(temp.name)
        self.addCleanup(self.state.db.close)
        self.c = c = object.__new__(Controller)
        c.state = self.state
        c.remote = '192.0.2.20'
        c.sip = SimpleNamespace(dialog=SimpleNamespace(acked=True, incoming=True, created=time.monotonic()-5), end=Mock())
        c.operations = collections.deque()
        c.pending_op = c.keep_pending = None
        c.auto_attempted = False
        c.last_keep = time.monotonic()
        c.client = SimpleNamespace(peers={}, request=Mock())

    def test_no_control_or_keepalive_before_sip_ack(self):
        c = self.c
        c.sip.dialog.acked = False
        c.last_keep = 0
        c.client.peers = {(c.remote,52102):object(),(c.remote,57703):object()}
        c.operations.append(('panelGetRelaysCommand', {'doormatic':False}, 'panelGetRelaysResponse', 'relays', None))
        c.service_operations()
        c.client.request.assert_not_called()
        self.assertEqual(len(c.operations), 1)
        c.sip.dialog.acked = True
        c.service_operations()
        self.assertEqual(c.client.request.call_count, 2)

    def test_automatic_open_once_and_only_incoming(self):
        c = self.c
        self.state.set_auto(0)
        self.state.allow_open, self.state.relays = True, ['relay']
        c.sip.dialog.incoming = False
        c.service_operations()
        self.assertFalse(c.operations)
        c.sip.dialog.incoming = True
        c.service_operations()
        c.service_operations()
        self.assertEqual(len(c.operations), 1)
        self.assertEqual(c.operations[0][1], {'doormatic':True})

    def test_cancel_auto_while_query_pending_does_not_open(self):
        self.state.allow_open = True
        self.state.set_auto(None)
        self.c.result('auto_relays', SimpleNamespace(error=None, result={'relayTags':['relay']}))
        self.assertFalse(self.c.operations)
        self.assertEqual(self.state.logs(limit=1)[0]['kind'], 'auto_skipped')

    def test_open_timeout_is_unknown_and_never_retried(self):
        self.c.result('open_manual', SimpleNamespace(error='timeout', result=None))
        self.assertEqual(self.state.logs(limit=1)[0]['kind'], 'open_unknown')
        self.assertFalse(self.c.operations)
        self.assertFalse(self.state.allow_open)

    def test_success_log_requires_positive_panel_response(self):
        self.c.result('open_manual', SimpleNamespace(error=None, result={'result':'DENIED'}))
        self.assertEqual(self.state.logs(limit=1)[0]['kind'], 'open_denied')
        self.c.result('open_manual', SimpleNamespace(error=None, result={'result':'PANEL_OPEN_DOOR_RESULT_OK'}))
        self.assertEqual(self.state.logs(limit=1)[0]['kind'], 'open_manual')

    def test_manual_request_id_survives_queue_and_all_outcomes(self):
        c = self.c
        self.state.call_id, self.state.panel_id = 'synthetic-call', 'hall'
        for response, error, kind in [
            ({'result':'PANEL_OPEN_DOOR_RESULT_OK'}, None, 'open_manual'),
            ({'result':'DENIED'}, None, 'open_denied'),
            (None, 'timeout', 'open_unknown'),
        ]:
            with self.subTest(kind=kind):
                self.state.allow_open, self.state.relays = True, ['relay']
                pending = SimpleNamespace(result=None, error=None)
                c.client.peers = {(c.remote,52102):object()}
                c.client.request.return_value = pending
                c.open(request_id='synthetic-request')
                c.service_operations()
                pending.result, pending.error = response, error
                c.service_operations()
                event = self.state.phone_snapshot(['hall'])['events'][0]
                self.assertEqual(event['kind'], kind)
                self.assertEqual(event['request_id'], 'synthetic-request')
                self.assertEqual(event['call_id'], 'synthetic-call')
                self.assertFalse(c.operations)
                self.assertIsNone(c.pending_op)

    def test_ending_removes_stale_peers_before_next_call(self):
        c = self.c
        c.control_peer, c.keep_peer = Mock(), Mock()
        peers = [c.control_peer, c.keep_peer]
        c.client.address = lambda peer: (c.remote, 52102 if peer is peers[0] else 57703)
        c.client.peers = {c.client.address(p):p for p in peers}
        c.client.pending = {address:object() for address in c.client.peers}
        c.video = Mock()
        c.notify('ended', {'reason':'BYE'})
        self.assertEqual(c.client.peers, {})
        self.assertEqual(c.client.pending, {})
        self.assertIsNone(c.control_peer)
        for peer in peers:
            peer.disconnect_now.assert_called_once()

    def test_phone_queued_control_cannot_move_to_next_call(self):
        c = self.c
        c.actions = queue.Queue()
        c.actions.put(('open',None,'request','previous-call',True))
        c.link_checked = time.monotonic()
        c.sockets, c.hosts = [], []
        c.sip.tick = Mock()
        c.announcer = Mock()
        c.service_operations = Mock()
        c.open = Mock()
        self.state.call_id = 'new-call'
        c.iteration()
        c.open.assert_not_called()
        self.assertEqual(self.state.logs(limit=1)[0]['kind'],'control_failed')
