"""Synthetic phone grants, scoped HTTP control and revocable state streams."""
import copy
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock

from fermax.api import server
from fermax.auth import Auth, set_password
from fermax.config import EXAMPLE
from fermax.phone import Devices
from fermax.state import State, atomic_json


PASSWORD = 'synthetic-phone-password'


class PhoneTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.config = copy.deepcopy(EXAMPLE)
        self.config['panels'].append({'id':'other','name':'Other entrance','ip':'192.0.2.21'})
        atomic_json(self.folder/'config.json', self.config)
        set_password(self.folder, PASSWORD)
        self.auth = Auth(self.folder)
        self.devices = Devices(self.auth)
        self.auth.devices = self.devices
        self.allowed = self.config['panels'][0]['id']
        self.state = State(self.folder, config=self.config)
        self.addCleanup(self.state.db.close)

    def grant(self):
        grant = self.devices.enroll('Kitchen', [self.allowed])
        session, device = self.devices.renew(grant)
        return grant, session, device

    def serve(self):
        service = server(self.state, self.auth, ('127.0.0.1',0))
        thread = threading.Thread(target=service.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(service.server_close)
        self.addCleanup(service.shutdown)
        self.service = service
        return service

    def request(self, method, path, data=None, cookie='', origin=None):
        conn = http.client.HTTPConnection(*self.service.server_address, timeout=4)
        headers = {'Cookie':cookie}
        if origin:
            headers['Origin'] = origin
        conn.request(method, path, None if data is None else json.dumps(data), headers)
        response = conn.getresponse()
        body = response.read()
        result = response.status, body, response.getheaders()
        conn.close()
        return result

    def test_grant_survives_restart_and_days_but_not_password_reset(self):
        now = [0.]
        self.devices.clock = lambda:now[0]
        grant, session, device = self.grant()
        now[0] = 2*86400
        self.assertIsNone(self.devices.authorized(session))
        renewed, _ = self.devices.renew(grant)
        self.assertEqual(self.devices.authorized(renewed)['id'], device['id'])
        restored = Devices(Auth(self.folder))
        renewed, _ = restored.renew(grant)
        self.assertIsNotNone(restored.authorized(renewed))
        set_password(self.folder, 'replacement-phone-password')
        self.assertIsNone(restored.authorized(renewed))
        self.assertIsNone(restored.renew(grant))
        self.assertIsNone(Devices(Auth(self.folder)).renew(grant))

    def test_grants_store_only_digest_and_cannot_authorize_admin(self):
        grant, session, _ = self.grant()
        content = (self.folder/'phone-devices.json').read_text()
        self.assertNotIn(grant, content)
        self.assertNotIn(session, content)
        self.assertEqual((self.folder/'phone-devices.json').stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.auth.authorized('',session))
        self.assertFalse(self.auth.authorized(grant,''))
        self.assertIsNone(self.devices.authorized(self.auth.login(PASSWORD)))

    def test_revoke_and_logout_survive_restart(self):
        grant, session, device = self.grant()
        self.devices.revoke(device['id'])
        self.assertIsNone(self.devices.authorized(session))
        self.assertIsNone(self.devices.renew(grant))
        grant, session, _ = self.grant()
        self.devices.revoke_grant(grant)
        self.assertIsNone(Devices(Auth(self.folder)).renew(grant))

    def test_enrollment_requires_admin_and_reauthentication_then_clears_admin(self):
        self.serve()
        data = {'name':'Kitchen','panels':[self.allowed],'password':PASSWORD}
        self.assertEqual(self.request('POST','/v1/phone/enroll',data)[0],401)
        session = self.auth.login(PASSWORD)
        cookie = 'fermax='+session
        self.assertEqual(self.request('POST','/v1/phone/enroll',dict(data,password='wrong'),cookie)[0],401)
        code, _, headers = self.request('POST','/v1/phone/enroll',data,cookie)
        self.assertEqual(code,200)
        cookies = [value for key,value in headers if key.lower() == 'set-cookie']
        self.assertTrue(any('fermax_device=' in value and 'Path=/v1/phone/session' in value and 'HttpOnly' in value and 'SameSite=Strict' in value for value in cookies))
        self.assertTrue(any(value.startswith('fermax=;') for value in cookies))
        self.assertFalse(self.auth.authorized('',session))

    def test_phone_endpoints_scoped_and_csrf_protected(self):
        self.serve()
        grant, session, _ = self.grant()
        cookie = 'fermax_phone='+session
        self.assertEqual(self.request('GET','/v1/config',cookie=cookie)[0],401)
        self.assertEqual(self.request('GET','/v1/logs/export',cookie=cookie)[0],401)
        self.assertEqual(self.request('POST','/v1/auto',{'minutes':0},cookie)[0],401)
        self.assertEqual(self.request('GET','/v1/phone/events',cookie=cookie,origin='http://foreign.example')[0],403)
        self.assertEqual(self.request('POST','/v1/phone/session',{},'fermax_device='+grant,'http://foreign.example')[0],403)
        self.assertEqual(self.request('POST','/v1/phone/control',{'action':'preview','panel':'other','request_id':'p'},cookie)[0],403)
        self.assertEqual(self.request('POST','/v1/phone/control',{'action':'open','call_id':'ended','request_id':'ended'},cookie)[0],400)
        self.state.network = 'ready'
        self.state.controller = Mock()
        self.state.call = 'early_video'
        self.state.call_id = 'call-A'
        self.state.panel_id = self.allowed
        self.state.allow_open, self.state.relays = True, ['relay']
        wrong = {'action':'open','call_id':'call-old','request_id':'old'}
        self.assertEqual(self.request('POST','/v1/phone/control',wrong,cookie)[0],400)
        self.state.controller.enqueue.assert_not_called()
        right = dict(wrong,call_id='call-A',request_id='one')
        self.assertEqual(self.request('POST','/v1/phone/control',right,cookie)[0],202)
        self.assertEqual(self.request('POST','/v1/phone/control',right,cookie)[0],202)
        self.state.controller.enqueue.assert_called_once_with('open',None,'one','call-A',True)
        self.assertFalse(self.state.policy['enabled'])

    def test_projection_hides_other_panels_identity_and_event_details(self):
        self.state.call_id, self.state.panel_id = 'other-call', 'other'
        self.state.call, self.state.panel = 'early_video','Private panel name'
        self.state.event('Sensitive event text','incoming',{'address':'192.0.2.21'})
        self.state.video_jpeg = b'image'
        self.state.video_updated = self.state.mono()
        body = self.state.stream_snapshot([self.allowed])
        text = json.dumps(body)
        self.assertNotIn('Sensitive',text)
        self.assertNotIn('192.0.2.21',text)
        self.assertNotIn('Private panel name',text)
        self.assertNotIn('identity',text)
        self.assertEqual(body['state']['call'],'busy')
        self.assertFalse(body['state']['video_ready'])
        self.serve()
        _,session,_ = self.grant()
        self.assertEqual(self.request('GET','/v1/phone/frame.jpg',cookie='fermax_phone='+session)[0],404)

    def test_stream_version_and_restart_epoch(self):
        first = self.state.stream_snapshot([self.allowed])
        again = self.state.stream_snapshot([self.allowed])
        self.assertEqual(first['event_id'],again['event_id'])
        self.state.network = 'ready'
        next_state = self.state.stream_snapshot([self.allowed])
        self.assertGreater(next_state['version'], first['version'])
        restored = State(self.folder,config=self.config)
        self.addCleanup(restored.db.close)
        self.assertNotEqual(restored.stream_snapshot([self.allowed])['epoch'], first['epoch'])

    def read_sse(self, response):
        lines = []
        while True:
            line = response.readline().decode()
            if not line or line == '\n':
                return ''.join(lines)
            lines.append(line)

    def test_stream_snapshot_after_stale_cursor_and_live_revocation(self):
        self.serve()
        _, session, device = self.grant()
        conn = http.client.HTTPConnection(*self.service.server_address, timeout=4)
        self.addCleanup(conn.close)
        conn.request('GET','/v1/phone/events',headers={'Cookie':'fermax_phone='+session,'Last-Event-ID':'previous-boot:100'})
        response = conn.getresponse()
        self.assertEqual(response.status,200)
        self.assertIn('event: snapshot',self.read_sse(response))
        self.devices.revoke(device['id'])
        self.assertIn('event: unauthorized',self.read_sse(response))
        self.assertEqual(response.read(),b'')

    def test_connection_budget_does_not_block_state_control(self):
        self.serve()
        _,session,_ = self.grant()
        for _ in range(12):
            self.assertTrue(self.state.stream_slots.acquire(blocking=False))
        try:
            self.assertEqual(self.request('GET','/v1/phone/events',cookie='fermax_phone='+session)[0],503)
            self.assertEqual(self.request('GET','/v1/phone/state',cookie='fermax_phone='+session)[0],200)
            self.state.event('still working')
        finally:
            for _ in range(12): self.state.stream_slots.release()

    def test_http_logout_clears_both_cookies_and_revokes_grant(self):
        self.serve()
        grant,session,_ = self.grant()
        code, _, headers = self.request('POST','/v1/phone/session/logout',{},'fermax_device='+grant)
        self.assertEqual(code,200)
        cookies = [v for k,v in headers if k.lower() == 'set-cookie']
        self.assertEqual(len(cookies),2)
        self.assertTrue(all('Max-Age=0' in value for value in cookies))
        self.assertIsNone(self.devices.authorized(session))
        self.assertIsNone(self.devices.renew(grant))
