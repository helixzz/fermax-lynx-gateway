import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from fermax.api import server
from fermax.auth import Auth, set_password
from fermax.protocol import Codec, SIP, Sessions
from fermax.state import State




class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = [2000000000., 100.]
        self.states = []
        def make():
            state = State(self.tmp.name, lambda:self.clock[0], lambda:self.clock[1])
            self.states.append(state)
            return state
        self.make = make
        self.addCleanup(lambda:[s.db.close() for s in self.states])
        self.state = self.make()

    def auth(self):
        set_password(self.tmp.name, 'test-password-long')
        (Path(self.tmp.name)/'api-token').write_text('test-token')
        return Auth(self.tmp.name)

    def test_unlimited_survives_restart_and_weeks(self):
        self.state.set_auto(0)
        self.clock[0] += 30*86400
        self.clock[1] += 30*86400
        restored = self.make()
        self.assertTrue(restored.snapshot()['auto']['enabled'])
        self.assertIsNone(restored.snapshot()['auto']['expires_at'])

    def test_finite_expires_after_restart(self):
        self.state.set_auto(15)
        self.clock[0] += 899
        self.clock[1] += 899
        restored = self.make()
        self.assertTrue(restored.snapshot()['auto']['enabled'])
        self.clock[0] += 2
        self.clock[1] += 2
        self.assertFalse(restored.snapshot()['auto']['enabled'])
        self.assertFalse(self.make().snapshot()['auto']['enabled'])

    def test_clock_rollback_cannot_extend_running_timer(self):
        self.state.set_auto(15)
        self.clock[0] -= 86400
        self.clock[1] += 901
        self.assertFalse(self.state.snapshot()['auto']['enabled'])

    def test_open_requires_permission_and_is_idempotent(self):
        class Controller:
            def __init__(self): self.actions=[]
            def enqueue(self, *args): self.actions.append(args)
        self.state.controller = Controller()
        self.state.network = 'ready'
        with self.assertRaises(ValueError):
            self.state.control('open')
        self.state.call, self.state.allow_open, self.state.relays = 'early_video', True, ['relay']
        self.state.control('open', request_id='unique')
        self.assertTrue(self.state.control('open', request_id='unique')['duplicate'])
        self.assertEqual(len(self.state.controller.actions), 1)
        with self.assertRaises(ValueError):
            self.state.control('hangup', request_id='unique')

    def test_full_journal_pagination_and_restart(self):
        for i in range(120):
            self.state.event('event '+str(i), 'test', {'index':i})
        newest = self.state.logs(limit=50)
        older = self.state.logs(before=newest[-1]['id'], limit=100)
        self.assertEqual(len(newest)+len(older), 120)
        self.assertEqual(self.make().logs(limit=1)[0]['detail'], {'index':119})

    def test_invalid_input_and_corrupt_file(self):
        for value in (True, -1, 7, '0', 1.5):
            with self.assertRaises(ValueError):
                self.state.set_auto(value)
        self.state.path.write_text('{broken')
        self.assertFalse(self.make().snapshot()['auto']['enabled'])

    def test_http_auth_and_live_control_rejected(self):
        service = server(self.state, self.auth(), ('127.0.0.1', 0))
        thread = threading.Thread(target=service.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(service.server_close)
        self.addCleanup(service.shutdown)
        conn = http.client.HTTPConnection(*service.server_address)
        self.addCleanup(conn.close)
        conn.request('POST', '/v1/auto', '{"minutes":0}', {'Content-Type':'application/json'})
        response = conn.getresponse()
        self.assertEqual(response.status, 401)
        response.read()
        conn.request('POST', '/v1/control', '{}', {'Authorization':'Bearer test-token'})
        response = conn.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        self.assertFalse(self.state.snapshot()['auto']['enabled'])

    def test_web_login_cookie_origin_and_full_export(self):
        service = server(self.state, self.auth(), ('127.0.0.1', 0))
        threading.Thread(target=service.serve_forever, daemon=True).start()
        self.addCleanup(service.server_close)
        self.addCleanup(service.shutdown)
        conn = http.client.HTTPConnection(*service.server_address)
        self.addCleanup(conn.close)
        conn.request('POST', '/v1/login', '{"password":"test-password-long"}')
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        cookie = response.getheader('Set-Cookie')
        self.assertIn('HttpOnly', cookie)
        self.assertIn('SameSite=Strict', cookie)
        response.read()
        headers = {'Cookie':cookie.split(';')[0], 'Origin':'http://untrusted.example'}
        conn.request('POST', '/v1/auto', '{"minutes":0}', headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 403)
        response.read()
        self.assertFalse(self.state.policy['enabled'])
        headers['Origin'] = 'http://127.0.0.1:'+str(service.server_address[1])
        conn.request('POST', '/v1/auto', '{"minutes":0}', headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        response.read()
        self.state.event('=formula', 'export-test', {'unicode':'门铃'})
        conn.request('GET', '/v1/logs/export', headers=headers)
        response = conn.getresponse()
        self.assertEqual(response.status, 200)
        content = response.read().decode('utf-8-sig')
        self.assertIn("'=formula", content)
        self.assertIn('门铃', content)
        self.assertIn('auto_changed', content)


class CalibrationTests(unittest.TestCase):
    def test_lcd_discovery_handles_changing_framebuffer_index(self):
        from fermax.display import find_framebuffer
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fb = root/'fb1'
            fb.mkdir()
            for name, value in [('name','fb_ili9486'), ('virtual_size','480,320'), ('bits_per_pixel','16')]:
                (fb/name).write_text(value)
            self.assertEqual(find_framebuffer(root), '/dev/fb1')
            fb.rename(root/'fb0')
            self.assertEqual(find_framebuffer(root), '/dev/fb0')

    def test_swapped_inverted_touch_axes(self):
        from fermax.display import affine, transform, TARGETS
        raw = [(4000-y*10, x*7+100) for x,y in TARGETS]
        coeff = affine(raw)
        for p, target in zip(raw, TARGETS):
            for a,b in zip(transform(coeff, p), target):
                self.assertAlmostEqual(a,b)


if __name__ == '__main__':
    unittest.main()
