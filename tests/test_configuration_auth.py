import copy
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from fermax.config import EXAMPLE, validate, load
from fermax.auth import Auth, set_password
from fermax.api import server
from fermax.state import State, atomic_json
from fermax.protocol import Codec, SIP
from fermax.sip_live import Signaling


class ConfigurationAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.config=copy.deepcopy(EXAMPLE)
        atomic_json(self.folder/'config.json',self.config)
        set_password(self.folder,'original-password-example')
        (self.folder/'api-token').write_text('independent-api-token')
        self.auth=Auth(self.folder)

    def test_configuration_rejects_duplicates_and_bad_networks(self):
        for key,value in [('monitor_ip','127.0.0.1'),('monitor_ip','224.0.0.1'),('home_interface','eth0'),('extension',8),('unit','x\r\nInjected: value')]:
            config=copy.deepcopy(self.config);config[key]=value
            with self.assertRaises(ValueError):validate(config)
        self.config['panels'].append(copy.deepcopy(self.config['panels'][0]))
        with self.assertRaises(ValueError):validate(self.config)

    def test_password_hash_and_cli_reset_revoke_sessions(self):
        session=self.auth.login('original-password-example')
        self.assertTrue(self.auth.authorized('',session))
        self.assertNotIn('original-password-example',(self.folder/'auth.json').read_text())
        self.assertFalse(self.auth.authorized('', 'independent-api-token'))
        self.assertFalse(self.auth.authorized('original-password-example',''))
        set_password(self.folder,'changed-password-example')
        self.assertFalse(self.auth.authorized('',session))
        self.assertFalse(self.auth.verify('original-password-example'))
        self.assertTrue(self.auth.verify('changed-password-example'))
        self.assertTrue(self.auth.authorized('independent-api-token',''))

    def test_logout_revokes_server_session(self):
        session=self.auth.login('original-password-example')
        self.auth.logout(session)
        self.assertFalse(self.auth.authorized('',session))

    def test_password_change_requires_current_password(self):
        with self.assertRaises(ValueError):self.auth.change('incorrect','changed-password-example')
        self.assertTrue(self.auth.verify('original-password-example'))
        with self.assertRaises(ValueError):self.auth.change('original-password-example','short')

    def test_web_config_password_and_session_revocation(self):
        state=State(self.folder,config=self.config)
        self.addCleanup(state.db.close)
        service=server(state,self.auth,('127.0.0.1',0))
        threading.Thread(target=service.serve_forever,daemon=True).start()
        self.addCleanup(service.server_close);self.addCleanup(service.shutdown)
        conn=http.client.HTTPConnection(*service.server_address)
        self.addCleanup(conn.close)
        cookie=self.auth.login('original-password-example')
        def request(method,path,data=None,authenticated=True):
            conn.request(method,path,None if data is None else json.dumps(data),{'Cookie':'fermax='+cookie} if authenticated else {})
            response=conn.getresponse();return response.status,json.loads(response.read())
        self.assertEqual(request('GET','/v1/config',authenticated=False)[0],401)
        updated=copy.deepcopy(self.config);updated['unit']='0202'
        state.call='early_video'
        self.assertEqual(request('POST','/v1/config',updated)[0],400)
        self.assertEqual(load(self.folder/'config.json'),self.config)
        state.call='idle'
        status,body=request('POST','/v1/config',updated)
        self.assertEqual(status,200);self.assertTrue(body['restart_required'])
        self.assertEqual(state.config['unit'],'0101')
        self.assertEqual(load(self.folder/'config.json')['unit'],'0202')
        self.assertEqual(request('POST','/v1/password',{'current_password':'original-password-example','new_password':'changed-password-example'})[0],200)
        self.assertEqual(request('GET','/v1/state')[0],401)
        self.assertTrue(self.auth.verify('changed-password-example'))
        self.assertNotIn('changed-password-example',json.dumps(state.logs()))

    def test_sip_identity_comes_from_configuration(self):
        sent=[]
        sip=Signaling('192.0.2.10',['192.0.2.20'],lambda data,peer:sent.append(data),lambda *args:None,unit='0202')
        sip.preview('192.0.2.20')
        parsed=SIP.parse(sent[0])
        self.assertEqual(parsed.headers['user-agent'],'0202 FermaxGateway')
        self.assertIn('192.0.2.10',parsed.body)

    def test_minimal_schema_known_wire_contract(self):
        codec=Codec(None,b'01234567ABCDEFGHabcdefgh')
        wire=codec.command('panelOpenDoorCommand',{'relayName':'relay','doormatic':True},b'\x01'*16)
        # Envelope field 100; command field 1300; a five-byte relay and bool.
        self.assertEqual(wire.hex(),'0a1001010101010101010101010101010101a2060ca251090a0572656c61791001')
        reply=codec.envelope('response','panelOpenDoorResponse',{'result':'PANEL_OPEN_DOOR_RESULT_OK'})
        self.assertEqual(codec.decode(reply)['[protobuffers.response]']['[protobuffers.panelOpenDoorResponse]']['result'],'PANEL_OPEN_DOOR_RESULT_OK')
