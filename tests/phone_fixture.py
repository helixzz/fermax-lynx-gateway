"""Loopback-only browser fixture. Does not import or construct a live controller."""
import io
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
        atomic_json(folder/'config.json', EXAMPLE)
        state = State(folder)
        state.network = 'ready'
        state.clock_status['synchronized'] = True
        actions = []
        held_requests = []
        hold_open = False
        image = Image.new('RGB',(640,360),'#486254')
        draw = ImageDraw.Draw(image)
        draw.rectangle((210,40,420,350), fill='#d9ddc3')
        draw.rectangle((240,80,390,350), fill='#192a23')
        draw.text((20,20),'SYNTHETIC ENTRANCE',fill='white')
        out = io.BytesIO(); image.save(out,format='JPEG'); picture = out.getvalue()

        def incoming(direction='incoming'):
            with state.lock:
                state.call, state.call_id = 'early_video', uuid.uuid4().hex
                state.panel_id = EXAMPLE['panels'][0]['id']
                state.panel = EXAMPLE['panels'][0]['name']
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
            def enqueue(self, action, panel, request_id, *context):
                actions.append(action)
                if action == 'preview': incoming('outgoing')
                elif action == 'hangup': end()
                elif action == 'open':
                    if hold_open: held_requests.append(request_id)
                    else: state.event('Synthetic confirmation','open_manual', {'request_id':request_id})

        state.controller = FakeController()
        auth = Auth(folder)
        service = server(state,auth,('127.0.0.1',0))
        threading.Thread(target=service.serve_forever,daemon=True).start()
        print(json.dumps({'port':service.server_address[1]}),flush=True)
        try:
            for line in sys.stdin:
                command = json.loads(line)['command']
                if command == 'incoming': incoming()
                elif command == 'end': end()
                elif command == 'hold_open': hold_open = True
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
                    state.db.close()
                    state = State(folder)
                    state.network = 'ready'
                    state.clock_status['synchronized'] = True
                    state.controller = FakeController()
                    auth = Auth(folder)
                    service = server(state,auth,('127.0.0.1',port))
                    threading.Thread(target=service.serve_forever,daemon=True).start()
                print(json.dumps({'actions':actions}),flush=True)
        finally:
            service.shutdown(); service.server_close(); state.db.close()


if __name__ == '__main__':
    main()
