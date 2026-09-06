"""Root-owned systemd helper: keep fbcon from overwriting the kiosk framebuffer."""
import sys
from pathlib import Path

if sys.argv[1:] not in (['detach'], ['restore']):
    raise SystemExit('usage: console.py detach|restore')
restore = sys.argv[1] == 'restore'
if not restore and not any((p/'name').read_text().strip() == 'fb_ili9486'
                           for p in Path('/sys/class/graphics').glob('fb[0-9]*')):
    raise SystemExit('LCD not ready; systemd will retry')
for console in Path('/sys/class/vtconsole').glob('vtcon*'):
    if 'frame buffer' in (console/'name').read_text():
        (console/'bind').write_text('1' if restore else '0')
