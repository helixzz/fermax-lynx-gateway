import argparse
import logging
import os
import secrets
import signal
import threading
import time
import socket
import struct
import subprocess
import json
from pathlib import Path

from .api import server
from .state import State
from .config import load
from .auth import Auth
from .admin import write_token


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, default=Path.home()/'.local/state/fermax')
    parser.add_argument('--display', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    args.state_dir.mkdir(parents=True, exist_ok=True)
    config = load(args.state_dir/'config.json')
    auth = Auth(args.state_dir)
    if not (args.state_dir/'api-token').exists():
        write_token(args.state_dir)
    state = State(args.state_dir, config=config)
    marker = args.state_dir/'live-initialized'
    if not marker.exists():
        state.set_auto(None)
        marker.write_text('1')
    from .protocol import Codec
    from .controller import Controller
    codec = Codec(None, (args.state_dir/'edk').read_bytes())
    controller = Controller(state, codec)
    state.controller = controller
    controller_thread = threading.Thread(target=controller.run, daemon=True)
    controller_thread.start()
    http = server(state, auth, ('127.0.0.1',config['web_port']))
    threading.Thread(target=http.serve_forever, daemon=True).start()
    def lan_and_clock():
        import fcntl
        lan, last_address = None, None
        while not stop.is_set():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    address = socket.inet_ntoa(fcntl.ioctl(sock.fileno(), 0x8915, struct.pack('256s', config['home_interface'].encode()))[20:24])
                if address != last_address:
                    if lan:
                        lan.shutdown()
                        lan.server_close()
                    lan = server(state, auth, (address, config['web_port']))
                    threading.Thread(target=lan.serve_forever, daemon=True).start()
                    last_address = address
                    state.event('局域网网站已启动', 'web_ready', {'url':f"http://{address}:{config['web_port']}"})
                ntp = Path('/run/fermax-ntp.json')
                info = json.loads(ntp.read_text()) if ntp.exists() else {'source':'unknown','servers':[]}
                info['synchronized'] = subprocess.check_output(['timedatectl','show','-p','NTPSynchronized','--value'],text=True,timeout=3).strip() == 'yes'
                with state.lock:
                    state.clock_status = info
            except Exception as error:
                logging.warning('LAN/time status: %s', error)
            stop.wait(10)
        if lan:
            lan.shutdown()
            lan.server_close()
    display = None
    if args.display:
        from .display import Display
        display = Display(state, args.state_dir)
        def run_display():
            try:
                display.run()
            except Exception:
                logging.exception('Display failed; HTTP remains available')
        threading.Thread(target=run_display, daemon=True).start()
    stop = threading.Event()
    threading.Thread(target=lan_and_clock, daemon=True).start()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    state.event('网关服务已启动', 'service_start')
    logging.info('Live gateway started')
    while not stop.wait(0.2):
        state.tick()
    if display:
        display.stopping.set()
    controller.stop.set()
    controller_thread.join(timeout=4)
    http.shutdown()
    http.server_close()


if __name__ == '__main__':
    main()
