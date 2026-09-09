"""Real loopback HTTP and queued controls; never contact a building network."""
import collections
import copy
import http.client
import json
import queue
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fermax.api import server
from fermax.auth import Auth, set_password
from fermax.config import EXAMPLE
from fermax.integrations import Integrations
from fermax.state import State, atomic_json
from tests.test_controller import Controller

PASSWORD = 'synthetic-integration-password'


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.config = copy.deepcopy(EXAMPLE)
        self.panel = self.config['panels'][0]['id']
        self.config['panels'].append({'id': 'other', 'name': 'Other', 'ip': '192.0.2.21'})
        atomic_json(self.folder/'config.json', self.config)
        set_password(self.folder, PASSWORD)
        self.auth = Auth(self.folder)
        self.state = State(self.folder, config=self.config)
        self.addCleanup(self.state.db.close)
        self.integrations = Integrations(self.auth, self.state)
        self.auth.integrations = self.integrations
        self.state.network = 'ready'

    def grant(self, permissions=None, panels=None):
        code = self.integrations.pairing('Synthetic HA', panels or [self.panel], permissions or ['state', 'events'])['code']
        return self.integrations.pair(code)

    def serve(self):
        self.service = server(self.state, self.auth, ('127.0.0.1', 0))
        threading.Thread(target=self.service.serve_forever, daemon=True).start()
        self.addCleanup(self.service.server_close)
        self.addCleanup(self.service.shutdown)

    def request(self, method, path, data=None, token='', cookie=''):
        connection = http.client.HTTPConnection(*self.service.server_address, timeout=4)
        headers = {'Authorization': 'Bearer '+token, 'Cookie': cookie}
        connection.request(method, path, None if data is None else json.dumps(data), headers)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        return response.status, json.loads(raw) if raw and response.getheader('Content-Type').startswith('application/json') else raw

    def stream(self, token, cursor=None):
        connection = http.client.HTTPConnection(*self.service.server_address, timeout=4)
        self.addCleanup(connection.close)
        headers = {'Authorization': 'Bearer '+token}
        if cursor is not None:
            headers['Last-Event-ID'] = cursor
        connection.request('GET', '/v1/integration/events', headers=headers)
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        return response

    def message(self, response):
        result = {}
        while True:
            line = response.readline().decode().rstrip('\r\n')
            if not line:
                break
            key, value = line.split(':', 1)
            result[key] = value.strip()
        if 'data' in result:
            result['data'] = json.loads(result['data'])
        return result

    def test_pairing_persistence_single_use_and_revision(self):
        code = self.integrations.pairing('HA', [self.panel], ['events', 'state'])['code']
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(self.integrations.pair, [code, code]))
        self.assertEqual(sum(value is not None for value in results), 1)
        grant = next(value for value in results if value)
        text = self.integrations.path.read_text()
        self.assertNotIn(grant['token'], text)
        self.assertNotIn(code, text)
        self.assertEqual(self.integrations.path.stat().st_mode & 0o777, 0o600)
        restored = Integrations(Auth(self.folder), self.state)
        self.assertEqual(restored.authorized(grant['token']), grant['integration'])
        self.assertEqual(restored.gateway(), self.integrations.gateway())
        code = self.integrations.pairing('Pending', [self.panel], ['events', 'state'])['code']
        set_password(self.folder, 'synthetic-replacement-password')
        self.assertIsNone(self.integrations.pair(code))
        self.assertIsNone(restored.authorized(grant['token']))

    def test_pairing_checks_expiry_current_scope_and_persistence_failure(self):
        now = [0]
        self.integrations.clock = lambda: now[0]
        code = self.integrations.pairing('HA', [self.panel], ['state', 'events'])['code']
        with patch.object(self.integrations, 'save', side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):
                self.integrations.pair(code)
        self.assertIsNotNone(self.integrations.pair(code))
        code = self.integrations.pairing('HA', [self.panel], ['state', 'events'])['code']
        now[0] = 300
        self.assertIsNone(self.integrations.pair(code))
        code = self.integrations.pairing('HA', [self.panel], ['state', 'events'])['code']
        self.state.config['panels'] = []
        with self.assertRaises(ValueError):
            self.integrations.pair(code)

    def test_revoke_cancels_pending_pairing(self):
        grant = self.grant()
        code = self.integrations.pairing('Pending', [self.panel], ['state', 'events'])['code']
        self.integrations.revoke(grant['integration']['id'])
        self.assertIsNone(self.integrations.authorized(grant['token']))
        self.assertIsNone(self.integrations.pair(code))

    def test_corrupted_store_fails_closed_without_crashing(self):
        self.serve()
        grant = self.grant()
        for value in ([], None, 'invalid', {'revision': self.auth.record['revision'], 'integrations': []}):
            with self.subTest(value=value):
                atomic_json(self.integrations.path, value)
                with self.assertRaises(ValueError):
                    self.integrations.authorized(grant['token'])
                self.assertEqual(self.request('GET', '/v1/integration/state', token=grant['token'])[0], 401)

    def test_admin_pairing_and_credential_separation(self):
        self.serve()
        body = {'password': PASSWORD, 'name': 'HA', 'panels': [self.panel], 'permissions': ['state', 'events']}
        self.assertEqual(self.request('POST', '/v1/integrations/pairing', body)[0], 401)
        cookie = 'fermax='+self.auth.login(PASSWORD)
        self.assertEqual(self.request('POST', '/v1/integrations/pairing', body | {'password': 'wrong'}, cookie=cookie)[0], 401)
        status, pairing = self.request('POST', '/v1/integrations/pairing', body, cookie=cookie)
        self.assertEqual(status, 200)
        status, grant = self.request('POST', '/v1/integration/pair', {'code': pairing['code']})
        self.assertEqual(status, 200)
        self.assertEqual(self.request('POST', '/v1/integration/pair', {'code': pairing['code']})[0], 401)
        token = grant['token']
        for path in ['/v1/state', '/v1/config', '/v1/logs/export', '/v1/integrations', '/v1/phone/state']:
            self.assertEqual(self.request('GET', path, token=token)[0], 401, path)
        self.assertEqual(self.request('GET', '/v1/integration/state', cookie=cookie)[0], 401)
        self.assertEqual(self.request('GET', '/v1/integration/state', token=token)[0], 200)
        self.assertEqual(self.request('POST', '/v1/integrations/revoke', {'password': PASSWORD, 'id': grant['integration']['id']}, cookie=cookie)[0], 200)
        self.assertEqual(self.request('GET', '/v1/integration/state', token=token)[0], 401)

    def test_projection_camera_and_panel_scope(self):
        self.serve()
        readonly = self.grant()
        camera = self.grant(['state', 'events', 'camera'])
        self.state.call, self.state.call_id = 'early_video', 'synthetic-call'
        self.state.panel_id, self.state.panel = 'other', 'Private entrance'
        self.state.allow_open = True
        self.state.video_jpeg, self.state.video_updated = b'synthetic-jpeg', self.state.mono()
        self.state.event('Sensitive text', 'incoming', {'address': '192.0.2.21'})
        status, snapshot = self.request('GET', '/v1/integration/state', token=readonly['token'])
        self.assertEqual(status, 200)
        self.assertEqual(snapshot['state']['call'], 'busy')
        self.assertFalse(snapshot['state']['allow_open'])
        for private in ('192.0.2.21', 'Private entrance', 'Sensitive text', 'monitor_ip', 'digest'):
            self.assertNotIn(private, json.dumps(snapshot))
        path = '/v1/integration/frame.jpg?panel='+self.panel
        self.assertEqual(self.request('GET', path, token=readonly['token'])[0], 403)
        self.assertEqual(self.request('GET', path, token=camera['token'])[0], 404)
        self.state.panel_id = self.panel
        self.assertEqual(self.request('GET', path, token=camera['token']), (200, b'synthetic-jpeg'))
        self.state.video_updated -= 6
        self.assertEqual(self.request('GET', path, token=camera['token'])[0], 404)

    def test_replay_over_multiple_batches_and_filtered_checkpoint(self):
        self.serve()
        grant = self.grant()
        start = self.integrations.head()
        for index in range(1005):
            self.state.event('Synthetic', 'incoming', {'panel_id': self.panel if index % 2 else 'other', 'call_id': str(index), 'secret': 'never project'})
        end = self.integrations.head()
        response = self.stream(grant['token'], self.integrations.cursor(start))
        first = self.message(response)
        self.assertEqual(first['event'], 'snapshot')
        self.assertNotIn('id', first)
        events, checkpoints = [], []
        while True:
            item = self.message(response)
            if item['event'] == 'ready':
                self.assertEqual(item['id'], self.integrations.cursor(end))
                break
            if item['event'] == 'event':
                events.append(item['data'])
            elif item['event'] == 'checkpoint':
                checkpoints.append(item['id'])
        self.assertEqual(len(events), 502)
        self.assertEqual(len(checkpoints), 3)
        self.assertTrue(all(e['replayed'] for e in events))
        self.assertEqual(len({e['id'] for e in events}), 502)
        self.assertNotIn('secret', json.dumps(events))
        self.state.event('New', 'incoming', {'panel_id': self.panel, 'call_id': 'live-call'})
        while True:
            item = self.message(response)
            if item['event'] == 'event':
                self.assertFalse(item['data']['replayed'])
                self.assertEqual(item['data']['call_id'], 'live-call')
                break

    def test_new_or_invalid_cursor_never_replays_old_events_and_revoke_closes(self):
        self.serve()
        grant = self.grant()
        self.state.event('Old', 'incoming', {'panel_id': self.panel})
        for cursor in (None, 'wrong-journal:5', self.integrations.cursor(self.integrations.head()+1)):
            response = self.stream(grant['token'], cursor)
            self.assertEqual(self.message(response)['event'], 'snapshot')
            item = self.message(response)
            if cursor:
                self.assertEqual(item['event'], 'reset')
                item = self.message(response)
            self.assertEqual(item['event'], 'ready')
            response.close()
        response = self.stream(grant['token'])
        self.message(response)
        self.integrations.revoke(grant['integration']['id'])
        for _ in range(5):
            if self.message(response).get('event') == 'unauthorized':
                break
        else:
            self.fail('stream did not revoke')
        self.assertEqual(response.read(), b'')

    def test_stream_budget_independent_from_phone_and_state(self):
        self.serve()
        grant = self.grant()
        for _ in range(4):
            self.assertTrue(self.integrations.slots.acquire(blocking=False))
        try:
            self.assertEqual(self.request('GET', '/v1/integration/events', token=grant['token'])[0], 503)
            self.assertEqual(self.request('GET', '/v1/integration/state', token=grant['token'])[0], 200)
            self.assertTrue(self.state.stream_slots.acquire(blocking=False))
            self.state.stream_slots.release()
        finally:
            for _ in range(4):
                self.integrations.slots.release()

    def control_body(self):
        return {'action': 'open', 'panel': self.panel, 'call_id': 'current-call', 'request_id': str(uuid.uuid4()), 'expires_at': self.state.wall()+20}

    def call(self):
        self.state.call, self.state.call_id, self.state.panel_id = 'early_video', 'current-call', self.panel
        self.state.allow_open, self.state.relays = True, ['synthetic-relay']

    def test_control_validation_idempotency_and_namespace(self):
        self.serve()
        self.call()
        self.state.controller = Mock()
        readonly = self.grant()
        grant = self.grant(['state', 'events', 'open'])
        other = self.grant(['state', 'events', 'open'])
        body = self.control_body()
        def post(data, token=grant['token']):
            return self.request('POST', '/v1/integration/control', data, token=token)
        self.assertEqual(post(body, readonly['token'])[0], 403)
        for field, value, status in [('panel', 'other', 403), ('call_id', 'stale', 409), ('request_id', 'bad', 400), ('expires_at', True, 400), ('expires_at', float('nan'), 400), ('expires_at', self.state.wall()-1, 409), ('expires_at', self.state.wall()+90, 409)]:
            self.assertEqual(post(body | {field: value})[0], status, field)
        self.state.controller.enqueue.assert_not_called()
        status, first = post(body)
        self.assertEqual(status, 202)
        self.assertFalse(first['duplicate'])
        self.assertTrue(post(body)[1]['duplicate'])
        self.state.controller.enqueue.assert_called_once()
        status, second = post(body, other['token'])
        self.assertEqual(status, 202)
        self.assertNotEqual(first['request_id'], second['request_id'])
        self.assertEqual(self.state.controller.enqueue.call_count, 2)

    @unittest.skipIf(Controller is None, 'python3-enet required')
    def test_revocation_and_staleness_at_both_dispatch_queues(self):
        self.serve()
        for stage in ('action', 'operation'):
            for change in ('revoke', 'password', 'panel', 'call', 'expiry', 'backward_clock', 'allow_open', 'relay', 'ending', 'corrupt_store'):
                with self.subTest(stage=stage, change=change):
                    self.state.config['panels'] = copy.deepcopy(self.config['panels'])
                    # State/config share the original object, so restore explicitly.
                    if not any(p['id'] == self.panel for p in self.state.config['panels']):
                        self.state.config['panels'] = copy.deepcopy(EXAMPLE['panels'])
                    self.call()
                    grant = self.grant(['state', 'events', 'open'])
                    c = object.__new__(Controller)
                    c.state, c.remote = self.state, '192.0.2.20'
                    c.actions, c.operations = queue.Queue(), collections.deque()
                    c.pending_op = c.keep_pending = None
                    c.auto_attempted, c.last_keep = True, time.monotonic()
                    c.sip = SimpleNamespace(dialog=SimpleNamespace(acked=True, incoming=True), tick=Mock(), end=Mock())
                    c.client = SimpleNamespace(peers={(c.remote, 52102): object()}, request=Mock())
                    c.link_checked, c.sockets, c.hosts, c.announcer = time.monotonic(), [], [], Mock()
                    self.state.controller = c
                    body = self.control_body()
                    self.assertEqual(self.request('POST', '/v1/integration/control', body, token=grant['token'])[0], 202)
                    if stage == 'operation':
                        with patch.object(c, 'service_operations'):
                            c.iteration()
                        self.assertEqual(len(c.operations), 1)
                    if change == 'revoke':
                        self.integrations.revoke(grant['integration']['id'])
                    elif change == 'password':
                        set_password(self.folder, 'synthetic-reset-password')
                    elif change == 'panel':
                        self.state.config['panels'] = []
                    elif change == 'call':
                        self.state.call_id = 'next-call'
                        self.state.panel_id = 'other'
                    elif change == 'allow_open':
                        self.state.allow_open = False
                    elif change == 'relay':
                        self.state.relays = ['replacement-relay'] if stage == 'operation' else []
                    elif change == 'ending':
                        self.state.call = 'ending'
                    elif change == 'corrupt_store':
                        atomic_json(self.integrations.path, [])
                    wall, mono = self.state.wall, self.state.mono
                    if change == 'expiry':
                        self.state.wall = lambda: body['expires_at']+1
                    elif change == 'backward_clock':
                        self.state.wall = lambda: body['expires_at']-25
                        self.state.mono = lambda: mono()+31
                    try:
                        c.iteration() if stage == 'action' else c.service_operations()
                    finally:
                        self.state.wall, self.state.mono = wall, mono
                    c.client.request.assert_not_called()
                    self.assertEqual(self.state.logs(limit=1)[0]['kind'], 'control_failed')
                    if change == 'corrupt_store':
                        self.integrations.save({})
                    if change == 'call':
                        detail = self.state.logs(limit=1)[0]['detail']
                        self.assertEqual(detail['panel_id'], self.panel)
                        self.assertEqual(detail['call_id'], 'current-call')
