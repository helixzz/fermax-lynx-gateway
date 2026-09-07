"""No real audio device, subprocess or building network in these tests."""
import io
import json
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from fermax.gateway_audio import GatewayAudio, candidates, outputs, builtin
from fermax.state import State

USB={'id':'a'*64,'name':'Synthetic USB','kind':'usb','pcm':'fake-usb'}
ANALOG={'id':'b'*64,'name':'Synthetic Analog','kind':'analog','pcm':'fake-analog'}
HDMI={'id':'c'*64,'name':'Synthetic HDMI','kind':'hdmi','pcm':'fake-hdmi'}
MUSIC={'ringtone':'chime','ring_seconds':15}


class FakePlayer:
    def __init__(self, fail=()): self.starts=[]; self.active=None; self.stops=0; self.fail=fail
    def start(self, device, pcm, rate, channels):
        self.active=device['id']; self.starts.append((device['id'],len(pcm)/(rate*channels*2),max(pcm)))
        if self.active in self.fail: raise OSError('Synthetic device busy')
    def poll(self): return None
    def stop(self):
        if self.active: self.stops+=1
        self.active=None


def wait(predicate):
    end=time.monotonic()+3
    while time.monotonic()<end:
        if predicate(): return
        time.sleep(.01)
    raise AssertionError('Timed out waiting for synthetic audio worker')


class GatewayAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.folder=Path(self.temp.name)
        self.state=State(self.folder); self.player=FakePlayer(); self.devices=[HDMI,ANALOG,USB]
        self.audio=GatewayAudio(self.folder,self.state.phone_preferences,discover=lambda:list(self.devices),player=self.player)
        self.state.gateway_audio=self.audio
        self.render=patch.object(self.audio,'phrase',return_value=(b'\x10\x00'*100,1000,1));self.render.start()
    def tearDown(self):
        self.audio.close();self.render.stop();self.state.db.close();self.temp.cleanup()
    def test_priority_and_preference(self):
        self.assertEqual([d['id'] for d in candidates(self.devices,'auto')],[USB['id'],ANALOG['id'],HDMI['id']])
        self.assertEqual(candidates(self.devices,HDMI['id'])[0],HDMI)
        self.assertEqual(candidates(self.devices,'d'*64)[0],USB)
    def test_persistence_validation_and_failed_write(self):
        self.assertTrue(self.audio.snapshot()['settings']['enabled'])
        value={'enabled':False,'volume':35,'output':USB['id']};self.audio.update(value)
        self.assertEqual(GatewayAudio(self.folder,None).value,value)
        for bad in [dict(value,volume=True),dict(value,volume=101),dict(value,output='hw:0'),dict(value,enabled='false')]:
            with self.assertRaises(ValueError): self.audio.update(bad)
        with patch('fermax.gateway_audio.atomic_json',side_effect=OSError):
            with self.assertRaises(OSError): self.audio.update(dict(value,enabled=True))
        self.assertEqual(self.audio.value,value)
    def test_bad_config_does_not_prevent_gateway_start(self):
        self.audio.path.write_text('broken')
        audio=GatewayAudio(self.folder,None)
        self.assertFalse(audio.value['enabled']);self.assertTrue(audio.config_error)
    def test_zero_phones_and_duplicate_call(self):
        self.audio.start();self.audio.call('visit',MUSIC,time.monotonic());wait(lambda:self.player.active)
        self.audio.call('visit',MUSIC,time.monotonic());time.sleep(.06)
        self.assertEqual(len(self.player.starts),1)
        self.audio.end();wait(lambda:self.player.active is None)
        self.assertEqual(self.player.stops,1)
    def test_disable_and_reenable_cannot_restart_visit(self):
        self.audio.start();self.audio.call('visit',MUSIC,time.monotonic());wait(lambda:self.player.active)
        self.audio.update(dict(self.audio.value,enabled=False));wait(lambda:not self.player.active)
        self.audio.update(dict(self.audio.value,enabled=True));self.audio.call('visit',MUSIC,time.monotonic());time.sleep(.06)
        self.assertEqual(len(self.player.starts),1)
    def test_failed_device_falls_back_with_remaining_time(self):
        self.player.fail=[USB['id']];self.audio.start()
        self.audio.call('visit',MUSIC,time.monotonic()-10);wait(lambda:self.player.active==ANALOG['id'])
        self.assertEqual([d[0] for d in self.player.starts],[USB['id'],ANALOG['id']])
        self.assertLessEqual(self.player.starts[-1][1],5)
        self.assertIn('降级',self.audio.status)
    def test_hot_unplug_and_no_switch_on_better_device(self):
        self.devices=[ANALOG];self.audio.start();self.audio.call('visit',MUSIC,time.monotonic());wait(lambda:self.player.active)
        self.devices=[USB,ANALOG];time.sleep(.6);self.assertEqual(self.player.active,ANALOG['id'])
        self.devices=[USB];wait(lambda:self.player.active==USB['id'])
        self.assertLess(self.player.starts[-1][1],self.player.starts[0][1])
    def test_no_devices_and_all_fail_are_bounded(self):
        self.player.fail=[d['id'] for d in self.devices];self.audio.start();self.audio.call('visit',MUSIC,time.monotonic())
        wait(lambda:self.audio.desired is None);self.assertEqual(len(self.player.starts),3);time.sleep(.06);self.assertEqual(len(self.player.starts),3)
        self.devices=[];self.audio.call('next',MUSIC,time.monotonic());wait(lambda:self.audio.desired is None);self.assertEqual(len(self.player.starts),3)
    def test_deadline_and_late_preparation(self):
        def late(_): self.audio.end();return b'\x00\x00'*100,1000,1
        self.audio.phrase=late;self.audio.start();self.audio.call('visit',MUSIC,time.monotonic());wait(lambda:self.audio.desired is None)
        self.assertEqual(self.player.starts,[])
    def test_test_preempted_and_stop_test_does_not_stop_visit(self):
        self.audio.start();self.audio.test();wait(lambda:self.player.active)
        self.audio.call('visit',MUSIC,time.monotonic());wait(lambda:len(self.player.starts)==2)
        self.audio.test(stop=True);time.sleep(.06);self.assertIsNotNone(self.player.active)
        self.audio.close();self.assertIsNone(self.player.active)
    def test_deadline_stops_once_and_expired_call_never_starts(self):
        self.audio.start();self.audio.call('short',dict(MUSIC,ring_seconds=.15),time.monotonic())
        wait(lambda:self.player.active);wait(lambda:self.audio.desired is None)
        self.assertIsNone(self.player.active);self.assertEqual(len(self.player.starts),1)
        self.audio.call('expired',MUSIC,time.monotonic()-60);wait(lambda:self.audio.desired is None)
        self.assertEqual(len(self.player.starts),1)

    def test_call_music_and_route_frozen(self):
        self.audio.call('visit',MUSIC,time.monotonic());job=self.audio.desired
        self.audio.update(dict(self.audio.value,output=HDMI['id'],volume=10));self.audio.start();wait(lambda:self.player.active)
        self.assertEqual(self.player.active,USB['id']);self.assertEqual(job['settings']['volume'],50)
    def test_state_incoming_only_and_end(self):
        self.state.call_id='preview';self.state.event('Synthetic preview','outgoing');self.assertIsNone(self.audio.desired)
        self.state.call_id='visit';self.state.event('Synthetic incoming','incoming');self.assertEqual(self.audio.desired['id'],'visit')
        self.state.event('Synthetic answered','answered');self.assertIsNone(self.audio.desired)
        self.state.call_id='visit2';self.state.event('Synthetic incoming','incoming');self.state.event('Synthetic end','call_ended');self.assertIsNone(self.audio.desired)


class DiscoveryTests(unittest.TestCase):
    def test_playback_filter_and_card_renumber(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);proc=root/'proc';sound=root/'sys';physical=root/'devices'/'usb-port'
            physical.mkdir(parents=True);(physical/'idVendor').write_text('0001');(physical/'idProduct').write_text('0002');(physical/'serial').write_text('synthetic')
            def make(n):
                card=proc/f'card{n}';(card/'pcm0p').mkdir(parents=True);(card/'pcm0c').mkdir();(card/'id').write_text('SyntheticUSB');(card/'pcm0p/info').write_text('name: USB Speaker\n')
                link=sound/f'card{n}';link.mkdir(parents=True);(link/'device').symlink_to(physical)
            make(0);first=outputs(proc,sound);self.assertEqual(len(first),1);self.assertEqual(first[0]['kind'],'usb')
            import shutil
            shutil.rmtree(proc/'card0');shutil.rmtree(sound/'card0');make(4)
            self.assertEqual(first[0]['id'],outputs(proc,sound)[0]['id'])
    def test_builtin_pcm_properties(self):
        from fermax.phone_preferences import CATALOG
        import array
        hashes=set()
        for track in CATALOG:
            pcm,rate,channels=builtin(track['id']);samples=array.array('h');samples.frombytes(pcm)
            self.assertEqual(channels,1);self.assertEqual(rate,24000);self.assertLess(len(samples)/rate,15)
            self.assertLessEqual(max(map(abs,samples)),8520);self.assertEqual(samples[0],0);self.assertEqual(samples[-1],0)
            hashes.add(hash(pcm))
        self.assertEqual(len(hashes),16)


class AudioApiTests(unittest.TestCase):
    def test_admin_only_persistence_and_no_control(self):
        import http.client
        import threading
        from fermax.api import server
        from fermax.auth import Auth, set_password
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);set_password(folder,'synthetic-audio-password');state=State(folder);auth=Auth(folder)
            service=server(state,auth,('127.0.0.1',0));threading.Thread(target=service.serve_forever,daemon=True).start()
            connection=http.client.HTTPConnection(*service.server_address)
            try:
                cookie=auth.login('synthetic-audio-password')
                def request(method,path,data=None,admin=True):
                    connection.request(method,path,json.dumps(data) if data is not None else None,{'Cookie':'fermax='+cookie} if admin else {})
                    response=connection.getresponse();return response.status,json.loads(response.read())
                for path in ('/v1/gateway-audio','/v1/gateway-audio/test'):
                    self.assertEqual(request('GET' if path.endswith('audio') else 'POST',path,{'stop':False},admin=False)[0],401)
                before=state.snapshot()['auto']
                value={'enabled':True,'volume':25,'output':'auto'}
                self.assertEqual(request('POST','/v1/gateway-audio',value)[0],200)
                self.assertEqual(request('GET','/v1/gateway-audio')[1]['settings'],value)
                self.assertEqual(request('POST','/v1/gateway-audio/test',{'stop':'false'})[0],400)
                state.call='early_video'
                self.assertEqual(request('POST','/v1/gateway-audio/test',{'stop':False})[0],400)
                state.call='idle'
                self.assertEqual(request('POST','/v1/gateway-audio/test',{'stop':False})[0],200)
                self.assertTrue(state.gateway_audio.snapshot()['testing'])
                self.assertEqual(request('POST','/v1/gateway-audio/test',{'stop':True})[0],200)
                self.assertFalse(state.gateway_audio.snapshot()['testing'])
                self.assertEqual(state.snapshot()['auto'],before)
            finally:
                connection.close();service.shutdown();service.server_close();state.db.close()

    def test_repeated_incoming_keeps_original_music_and_deadline(self):
        from tests.test_phone_preferences import music
        with tempfile.TemporaryDirectory() as tmp:
            state=State(Path(tmp))
            try:
                original=state.phone_preferences.upload(music());state.phone_preferences.update({'ringtone':'custom','ring_seconds':15})
                state.call_id='synthetic-call';state.event('Incoming','incoming');job=state.gateway_audio.desired
                state.phone_preferences.upload(music(b'\x20\x00'));state.phone_preferences.update({'ringtone':'marimba','ring_seconds':60})
                state.event('Repeated','incoming')
                self.assertIs(state.gateway_audio.desired,job)
                self.assertEqual(state.call_ring_preferences['music_revision'],original['music_revision'])
                self.assertIsNotNone(state.phone_preferences.audio(original['music_revision']))
            finally: state.db.close()
