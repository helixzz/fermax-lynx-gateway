import importlib.util
import os
import time
import unittest
from pathlib import Path

from fermax.protocol import Codec


@unittest.skipUnless(importlib.util.find_spec('enet'), 'Requires python3-enet (available on Pi)')
class TransportTests(unittest.TestCase):
    def setUp(self):
        from fermax.transport import Transport
        self.codec = Codec(None, b'01234567ABCDEFGHabcdefgh')
        self.client, self.panel = Transport(self.codec), Transport(self.codec)
        self.addCleanup(self.client.close)
        self.addCleanup(self.panel.close)
        self.peer = self.client.connect('127.0.0.1', self.panel.port)
        deadline = time.monotonic()+3
        while not (self.client.peers and self.panel.peers):
            self.client.poll(2)
            self.panel.poll(2)
            self.assertLess(time.monotonic(), deadline, 'ENet connect timed out')

    def test_encrypted_reliable_exchange_and_distinct_response_uuid(self):
        pending = self.client.request(self.peer, 'panelGetRelaysCommand', {'doormatic':False}, 'panelGetRelaysResponse')
        deadline = time.monotonic()+3
        while pending.result is None and pending.error is None:
            event = self.panel.poll(2)
            if event and event[0] == 'message':
                self.assertIn('[protobuffers.command]', event[2])
                response = self.codec.envelope('response', 'panelGetRelaysResponse', {'relayTags':['test-relay']})
                self.assertNotEqual(event[2]['uuid'], self.codec.decode(response)['uuid'])
                self.panel.send(event[1], response)
            self.client.poll(2)
            self.assertLess(time.monotonic(), deadline)
        self.assertEqual(pending.result, {'relayTags':['test-relay']})

    def test_timeout_and_outstanding_request_guard(self):
        pending = self.client.request(self.peer, 'panelGetRelaysCommand', {'doormatic':False}, 'panelGetRelaysResponse', timeout=0.1)
        with self.assertRaises(ValueError):
            self.client.request(self.peer, 'panelGetRelaysCommand', {}, 'panelGetRelaysResponse')
        deadline = time.monotonic()+2
        while pending.error is None:
            self.panel.poll(2)
            self.client.poll(2)
            self.assertLess(time.monotonic(), deadline)
        self.assertEqual(pending.error, 'timeout')
        self.assertFalse(self.client.peers)

    def test_building_address_rejected(self):
        with self.assertRaises(ValueError):
            self.client.connect('192.0.2.20', 52102)

    def test_request_diagnostics_count_invalid_and_unexpected_responses(self):
        import enet
        pending = self.client.request(self.peer, 'panelGetRelaysCommand',
                                      {'doormatic':False}, 'panelGetRelaysResponse')
        peer = next(iter(self.panel.peers.values()))
        peer.send(0, enet.Packet(b'invalid', enet.PACKET_FLAG_RELIABLE))
        self.panel.host.flush()
        self.panel.send(peer, self.codec.envelope('response', 'sessionKeepAliveResponse', {'state':True}))
        deadline = time.monotonic()+3
        while pending.received < 2:
            self.panel.poll(2)
            self.client.poll(2)
            self.assertLess(time.monotonic(), deadline)
        self.assertEqual((pending.received, pending.invalid, pending.unexpected_responses), (2, 1, 1))
        self.assertIsNone(pending.result)
        pending.deadline = time.monotonic()-1
        self.client.poll()
        self.assertEqual(pending.error, 'timeout')

    def test_fresh_host_after_timeout_ignores_old_session_reply(self):
        from fermax.transport import Transport
        old_panel_peer = next(iter(self.panel.peers.values()))
        expired = self.client.request(self.peer, 'panelGetRelaysCommand',
                                      {'doormatic':False}, 'panelGetRelaysResponse')
        expired.deadline = time.monotonic()-1
        self.client.poll()
        self.assertEqual(expired.error, 'timeout')
        # A panel can already have queued an answer as the old session expires.
        self.panel.send(old_panel_peer, self.codec.envelope(
            'response', 'panelGetRelaysResponse', {'relayTags':['stale-relay']}))
        fresh = Transport(self.codec)
        self.addCleanup(fresh.close)
        peer = fresh.connect('127.0.0.1', self.panel.port)
        deadline = time.monotonic()+3
        while not (fresh.peers and ('127.0.0.1', fresh.port) in self.panel.peers):
            fresh.poll(2)
            self.panel.poll(2)
            self.assertLess(time.monotonic(), deadline)
        pending = fresh.request(peer, 'panelGetRelaysCommand',
                                {'doormatic':False}, 'panelGetRelaysResponse')
        for _ in range(10):
            self.panel.poll(2)
            fresh.poll(2)
        self.assertIsNone(pending.result)
        self.assertIsNone(pending.error)
        self.panel.send(self.panel.peers[('127.0.0.1', fresh.port)], self.codec.envelope(
            'response', 'panelGetRelaysResponse', {'relayTags':['fresh-relay']}))
        while pending.result is None:
            self.panel.poll(2)
            fresh.poll(2)
            self.assertLess(time.monotonic(), deadline)
        self.assertEqual(pending.result, {'relayTags':['fresh-relay']})
