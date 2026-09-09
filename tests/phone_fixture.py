"""Loopback-only browser fixture. Does not import or construct a live controller."""
import copy
from contextlib import nullcontext
import datetime
import io
import os
import json
import sys
import tempfile
import threading
import uuid
from pathlib import Path

from PIL import Image, ImageDraw
from fermax.api import server
from fermax.auth import Auth, set_password
from fermax.config import EXAMPLE
from fermax.state import State, atomic_json


def main():
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        set_password(folder, 'synthetic-phone-password')
        config = copy.deepcopy(EXAMPLE)
        config['building'] = '示例之家'
        config['panels'][0]['name'] = '花园入口'
        config['panels'].append({'id':'side','name':'侧门入口','ip':'192.0.2.21'})
        atomic_json(folder/'config.json', config)
        demo = '--demo' in sys.argv
        fixed_time = datetime.datetime(2030,5,18,14,32,8,tzinfo=datetime.timezone.utc).timestamp()
        state = State(folder,config=config,wall=(lambda:fixed_time) if demo else __import__('time').time)
        state.network = 'ready'
        state.clock_status['synchronized'] = True
        actions = []
        held_requests = []
        hold_open = False
        image = Image.new('RGB',(800,600),'#b5b7a0')
        draw = ImageDraw.Draw(image)
        # Original geometric architecture illustration: no camera footage or real site.
        draw.rectangle((0,0,800,430),fill='#a4aa93')
        draw.polygon([(0,0),(170,110),(170,465),(0,600)],fill='#708776')
        draw.polygon([(800,0),(656,110),(656,465),(800,600)],fill='#c8c7ac')
        draw.polygon([(0,600),(170,425),(656,425),(800,600)],fill='#888f7b')
        for y in (455,495,545): draw.line((0,y,800,y),fill='#a5ad96',width=2)
        for x in (0,160,330,500,680,800): draw.line((400,360,x,600),fill='#a5ad96',width=2)
        draw.rectangle((210,66,606,445),fill='#d8d7be')
        draw.rectangle((235,88,582,440),fill='#263d34')
        draw.rectangle((248,102,565,425),fill='#40564a')
        for x in range(250,566,26): draw.line((x,104,x,422),fill='#4b6250',width=3)
        draw.rectangle((380,104,384,423),fill='#21372e')
        draw.rectangle((390,261,395,322),fill='#c7b981')
        draw.rectangle((410,261,415,322),fill='#c7b981')
        draw.rectangle((535,238,550,291),fill='#182b24')
        draw.rectangle((237,440,584,451),fill='#6b7765')
        draw.polygon([(281,472),(525,472),(552,508),(255,508)],fill='#4a5d4c')
        draw.rectangle((640,337,700,449),fill='#8d6e4a')
        draw.ellipse((638,325,702,349),fill='#3b4530')
        for x,y in [(648,251),(680,228),(652,286),(695,278),(673,311),(628,275)]:
            draw.line((670,339,x,y),fill='#3c5940',width=6)
            draw.ellipse((x-22,y-28,x+22,y+15),fill='#4a6f49')
        draw.rectangle((80,92,129,133),fill='#e9dbab')
        draw.rectangle((730,92,775,133),fill='#e9dbab')
        draw.text((24,563),'SYNTHETIC DEMO / 4:3',fill='#eff0d8')
        out = io.BytesIO(); image.save(out,format='JPEG'); picture = out.getvalue()

        def incoming(direction='incoming'):
            with state.lock:
                state.call, state.call_id = 'early_video', uuid.uuid4().hex
                state.panel_id = EXAMPLE['panels'][0]['id']
                state.panel = config['panels'][0]['name']
                state.direction = direction
                state.video_jpeg, state.video_updated = picture, state.mono()
                state.allow_open, state.relays = True, ['synthetic-relay']
                state.event('Synthetic call',direction)

        def end():
            with state.lock:
                state.event('Synthetic end','call_ended')
                state.call = 'idle'
                state.call_id = state.panel_id = state.direction = state.panel = None
                state.video_jpeg = None
                state.allow_open, state.relays = False, []

        class FakeController:
            def enqueue(self, action, panel, request_id, *context, guard=None):
                with state.lock, guard() if guard else nullcontext():
                    self.execute(action, panel, request_id)

            def execute(self, action, panel, request_id):
                actions.append(action)
                if action == 'preview': incoming('outgoing')
                elif action == 'hangup': end()
                elif action == 'open':
                    if hold_open: held_requests.append(request_id)
                    else: state.event('Synthetic confirmation','open_manual', {'request_id':request_id})

        class SilentPlayer:
            # Synthetic backend: never opens a PCM, speaker, or subprocess.
            def start(self, *args): pass
            def poll(self): return None
            def stop(self): pass

        audio_devices = [
            {'id':'a'*64,'name':'示例 USB 扬声器','kind':'usb','pcm':'synthetic-usb'},
            {'id':'b'*64,'name':'示例 3.5mm 输出','kind':'analog','pcm':'synthetic-analog'},
            {'id':'c'*64,'name':'示例 HDMI 显示器','kind':'hdmi','pcm':'synthetic-hdmi'}]
        def start_audio(target):
            target.gateway_audio.discover=lambda:list(audio_devices)
            target.gateway_audio.player=SilentPlayer()
            target.gateway_audio.start()

        start_audio(state)
        state.controller = FakeController()
        auth = Auth(folder)
        service = server(state,auth,('127.0.0.1',0))
        threading.Thread(target=service.serve_forever,daemon=True).start()
        print(json.dumps({'port':service.server_address[1]}),flush=True)
        try:
            for line in sys.stdin:
                command = json.loads(line)['command']
                if command == 'stats_seed':
                    for i in range(7): state.event('Synthetic daily visit','incoming',{'call_id':'daily-'+str(i),'panel_id':EXAMPLE['panels'][0]['id']})
                    for i in range(4): state.event('Synthetic daily confirmation','open_manual',{'request_id':'daily-open-'+str(i),'panel_id':EXAMPLE['panels'][0]['id']})
                elif command == 'stats_unavailable': state.statistics.available=False
                elif command == 'stats_large':
                    state.statistics.snapshot(state.wall())
                    state.statistics.cache=(state.statistics.cache[0],[('incoming',EXAMPLE['panels'][0]['id'],12345),('openings',EXAMPLE['panels'][0]['id'],123456)])
                elif command == 'stats_restore':
                    state.statistics.available=True
                    state.statistics.cache=None
                elif command == 'incoming': incoming()
                elif command == 'end': end()
                elif command == 'expire_ring':
                    state.call_started_mono -= 61
                    state.event('Synthetic elapsed ringing window','info')
                elif command == 'video_stale':
                    state.video_updated = state.mono()-10
                elif command == 'network_down': state.network = 'disconnected'
                elif command == 'network_up': state.network = 'ready'
                elif command == 'auto': state.set_auto(0)
                elif command == 'auto_off': state.set_auto(None)
                elif command == 'auto_expire':
                    state.deadline = state.mono()-1
                    state.tick()
                elif command == 'hold_open': hold_open = True
                elif command == 'audio_none': audio_devices.clear()
                elif command == 'audio_restore':
                    audio_devices.extend([
                        {'id':'a'*64,'name':'示例 USB 扬声器','kind':'usb','pcm':'synthetic-usb'},
                        {'id':'b'*64,'name':'示例 3.5mm 输出','kind':'analog','pcm':'synthetic-analog'}])
                elif command.startswith('lcd_') and demo and os.environ.get('DEMO_DIR'):
                    from fermax.display import Display
                    display=Display(state,folder,framebuffer='/dev/null',font_path=os.environ.get('DEMO_FONT'))
                    display.coeff=[[1,0,0],[0,1,0]]
                    display.page={'lcd_home':'home','lcd_settings':'settings','lcd_sound':'sound','lcd_outputs':'outputs'}[command]
                    display.render().save(str(Path(os.environ['DEMO_DIR'])/(command.replace('_','-')+'.webp')),'WEBP',quality=88)
                elif command == 'other_result':
                    state.event('Synthetic other client', 'open_denied', {'request_id':'other-client-request'})
                elif command == 'complete_open':
                    state.event('Synthetic confirmation', 'open_manual', {'request_id':held_requests.pop(0)})
                    hold_open = False
                elif command == 'revoke':
                    for device in auth.devices.list(): auth.devices.revoke(device['id'])
                elif command == 'reset_password': set_password(folder,'new-synthetic-password')
                elif command == 'restart':
                    port = service.server_address[1]
                    service.shutdown(); service.server_close()
                    state.gateway_audio.close(); state.db.close()
                    state = State(folder,config=config,wall=(lambda:fixed_time) if demo else __import__('time').time)
                    start_audio(state)
                    state.network = 'ready'
                    state.clock_status['synchronized'] = True
                    state.controller = FakeController()
                    auth = Auth(folder)
                    service = server(state,auth,('127.0.0.1',port))
                    threading.Thread(target=service.serve_forever,daemon=True).start()
                print(json.dumps({'actions':actions}),flush=True)
        finally:
            state.gateway_audio.close(); service.shutdown(); service.server_close(); state.db.close()


if __name__ == '__main__':
    main()
