"""Synthetic controller failures; no sockets or building commands are sent."""
import collections
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fermax.state import State
try:
    from fermax.controller import Controller
    from fermax.transport import Pending, Transport
    import enet
except ModuleNotFoundError as error:
    if error.name != 'enet':
        raise
    Controller = None


@unittest.skipIf(Controller is None, 'python3-enet required')
class RecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.state = State(temp.name)
        self.addCleanup(self.state.db.close)
        self.now = 100.0
        timer = patch('time.monotonic', side_effect=lambda: self.now)
        timer.start()
        self.addCleanup(timer.stop)
        self.transports = []
        factory = patch('fermax.controller.Transport', side_effect=self.transport)
        factory.start()
        self.addCleanup(factory.stop)
        c = self.c = object.__new__(Controller)
        c.state, c.codec, c.own = self.state, Mock(), '192.0.2.10'
        c.panels, c.names = {'hall':'192.0.2.20'}, {'192.0.2.20':'Synthetic panel'}
        c.hosts, c.operations = [], collections.deque()
        c.control_client, c.control_peer = None, None
        c.client = SimpleNamespace(connect=Mock(), peers={}, pending={}, address=Mock())
        c.video = Mock()
        c.sip = SimpleNamespace(dialog=SimpleNamespace(acked=True, incoming=True, created=95), end=Mock())
        c.notify('incoming', '192.0.2.20')

    def transport(self, *args, **kwargs):
        t = object.__new__(Transport)
        t.codec = self.c.codec
        t.host = SimpleNamespace(service=Mock(return_value=SimpleNamespace(type=enet.EVENT_TYPE_NONE)))
        t.peers, t.pending = {}, {}
        t.connect = Mock(return_value=Mock())
        t.send = Mock()
        self.transports.append(t)
        return t

    def connected(self):
        t = self.c.control_client
        peer = self.c.control_peer
        peer.address.host, peer.address.port = '192.0.2.20', 52102
        t.peers[('192.0.2.20', 52102)] = peer
        return t

    def reply(self, result):
        pending = self.c.pending_op[0]
        pending.result = result
        self.c.control_client.pending.clear()
        self.c.service_operations()

    def test_timeout_reconnects_requeries_then_allows_one_auto_open(self):
        c = self.c
        self.state.set_auto(0)
        original = self.connected()
        c.service_operations()
        expired = c.pending_op[0]
        self.now += 3.1
        original.poll()  # Exercise the actual transport timeout/reset defect.
        self.assertEqual(expired.error, 'timeout')
        c.service_operations()
        self.assertEqual(len(self.transports), 2)
        self.assertIsNone(original.host)
        self.assertNotIn(original, c.hosts)
        self.assertEqual(self.state.control_health, 'retrying')
        diagnostic = self.state.logs(limit=1)[0]['detail']
        self.assertEqual(diagnostic['received'], 0)
        self.assertEqual(diagnostic['invalid'], 0)
        self.assertEqual(diagnostic['request_ms'], 3100)
        self.assertFalse(self.state.allow_open)
        self.assertEqual(c.client.connect.call_count, 1)  # Keepalive is untouched.
        current = self.connected()
        c.service_operations()
        self.assertEqual(c.pending_op[1], 'relays')
        expired.result = {'relayTags':['stale-relay']}
        c.service_operations()
        self.assertEqual(self.state.relays, [])
        self.reply({'relayTags':['synthetic-relay']})
        self.assertEqual(c.pending_op[1], 'permission')
        self.reply({'allowOpenDoor':True})
        self.assertEqual(self.state.control_health, 'ready')
        c.service_operations()
        self.assertEqual(c.pending_op[1], 'auto_relays')
        self.reply({'relayTags':['synthetic-relay']})
        self.assertEqual(c.pending_op[1], 'open_auto')
        self.reply({'result':'PANEL_OPEN_DOOR_RESULT_OK'})
        for _ in range(100):
            c.service_operations()
        commands = [call.args[0] for call in c.codec.command.call_args_list]
        self.assertEqual(commands.count('panelOpenDoorCommand'), 1)
        self.assertEqual(len(self.state.logs(kind='open_auto')), 1)
        self.assertEqual(current.send.call_count, 4)

    def test_permission_disconnect_restarts_both_read_only_queries(self):
        c = self.c
        t = self.connected()
        c.service_operations()
        self.reply({'relayTags':['old-relay']})
        t.host.service.return_value = SimpleNamespace(type=enet.EVENT_TYPE_DISCONNECT, peer=c.control_peer)
        t.poll()
        c.service_operations()
        self.assertEqual(len(self.transports), 2)
        self.assertEqual(self.state.relays, [])
        self.assertFalse(self.state.allow_open)
        self.connected()
        c.service_operations()
        self.assertEqual(c.pending_op[1], 'relays')

    def test_connection_attempts_are_bounded_without_busy_loop_logging(self):
        c = self.c
        c.service_operations()
        for _ in range(3):
            self.now += 3.1
            c.service_operations()
        self.assertEqual(len(self.transports), 3)
        self.assertEqual(self.state.control_health, 'failed')
        self.assertFalse(c.operations)
        self.assertIsNone(c.control_client)
        events = len(self.state.logs())
        for _ in range(100):
            c.service_operations()
        self.assertEqual(len(self.state.logs()), events)
        self.assertFalse(self.state.allow_open)

    def test_total_budget_cancels_even_a_pending_request(self):
        c = self.c
        self.connected()
        c.service_operations()
        pending = c.pending_op[0]
        self.now += 12.1
        c.service_operations()
        self.assertEqual(pending.error, 'closed')
        self.assertEqual(self.state.control_health, 'failed')
        self.assertFalse(c.operations)
        self.assertIsNone(c.pending_op)

    def test_no_retry_before_ack_and_budget_starts_at_ack(self):
        c = self.c
        c.sip.dialog.acked = False
        self.now += 20
        c.service_operations()
        self.assertEqual(len(self.transports), 1)
        self.assertIsNone(c.discovery['attempt_started'])
        c.sip.dialog.acked = True
        c.service_operations()
        self.assertEqual(c.discovery['started'], self.now)
        self.assertEqual(len(self.transports), 1)

    def test_call_end_cancels_recovery_and_new_call_has_fresh_budget(self):
        c = self.c
        self.connected()
        c.service_operations()
        previous, pending = c.control_client, c.pending_op[0]
        old_call = self.state.call_id
        c.notify('ended', {})
        self.assertIsNone(c.discovery)
        self.assertIsNone(previous.host)
        self.assertEqual(self.state.control_health, 'idle')
        c.notify('incoming', '192.0.2.20')
        self.assertNotEqual(old_call, self.state.call_id)
        pending.result = {'relayTags':['old-call-relay']}
        self.connected()
        c.service_operations()
        self.assertEqual(self.state.relays, [])
        self.assertEqual(c.discovery['attempt'], 1)

    def test_doormatic_query_and_open_outcomes_are_never_replayed(self):
        c = self.c
        for purpose in ('auto_relays', 'open_auto', 'open_manual'):
            with self.subTest(purpose=purpose):
                c.discovery = None
                c.operations.clear()
                c.pending_op = (Pending('unused', self.now, error='timeout'), purpose, 'synthetic-request')
                self.state.allow_open, self.state.relays = True, ['synthetic-relay']
                c.service_operations()
                for _ in range(100):
                    c.service_operations()
                self.assertEqual(len(self.transports), 1)
                self.assertFalse(c.operations)
                self.assertFalse(self.state.allow_open)
                self.assertEqual(self.state.control_health, 'failed')

    def test_open_cannot_enter_queue_during_discovery(self):
        self.state.allow_open, self.state.relays = True, ['synthetic-relay']
        with self.assertRaises(ValueError):
            self.c.open()
        self.assertEqual([op[3] for op in self.c.operations], ['relays', 'permission'])

    def test_ending_does_not_start_another_recovery_attempt(self):
        self.c.service_operations()
        self.state.call = 'ending'
        self.now += 4
        self.c.service_operations()
        self.assertEqual(len(self.transports), 1)

    def test_ready_disconnect_disables_opening_and_cancels_queued_request(self):
        c = self.c
        self.connected()
        c.service_operations()
        self.reply({'relayTags':['synthetic-relay']})
        self.reply({'allowOpenDoor':True})
        c.open(request_id='synthetic-request')
        c.control_client.peers.clear()
        c.service_operations()
        self.assertEqual(self.state.control_health, 'failed')
        self.assertFalse(self.state.allow_open)
        self.assertFalse(c.operations)
        event = self.state.logs(kind='control_failed')[0]
        self.assertEqual(event['detail']['request_id'], 'synthetic-request')
        self.assertEqual(len(self.transports), 1)

    def test_send_failure_recovers_only_read_only_discovery(self):
        t = self.connected()
        t.send.side_effect = OSError('synthetic send failure')
        self.c.service_operations()
        self.assertEqual(len(self.transports), 2)
        self.assertEqual(self.state.control_health, 'retrying')
        self.assertEqual(self.state.logs(limit=1)[0]['detail']['reason'], 'send_failed')

    def test_recovery_keeps_application_keepalive_running(self):
        c = self.c
        c.client.peers[(c.remote, 57703)] = object()
        c.client.request = Mock(return_value=Pending('sessionKeepAliveResponse', self.now+3))
        c.service_operations()
        c.client.request.assert_called_once()
        self.assertEqual(c.client.request.call_args.args[1], 'sessionKeepAliveCommand')
        self.assertEqual(self.state.control_health, 'connecting')

    def test_repeated_calls_do_not_accumulate_control_hosts(self):
        c = self.c
        for _ in range(30):
            self.connected()
            c.service_operations()
            self.assertEqual(len(c.hosts), 1)
            c.notify('ended', {})
            self.assertFalse(c.hosts)
            self.assertIsNone(c.control_client)
            c.notify('incoming', '192.0.2.20')
        self.assertTrue(all(t.host is None for t in self.transports[:-1]))


if __name__ == '__main__':
    unittest.main()
