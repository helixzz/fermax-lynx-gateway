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
