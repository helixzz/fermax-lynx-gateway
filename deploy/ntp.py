#!/usr/bin/python3
"""NetworkManager dispatcher: use wlan0 DHCP option 42, otherwise public NTP."""
import ipaddress
import json
import os
import re
from pathlib import Path
import subprocess
import sys

PUBLIC = ['0.pool.ntp.org', '1.pool.ntp.org', '2.pool.ntp.org']


def servers(options):
    result = []
    for line in options.splitlines():
        value_line = line.split(':', 1)[1].strip() if line.startswith('DHCP4.OPTION[') else line.strip()
        if value_line.startswith('ntp_servers = '):
            for value in value_line.split(' = ', 1)[1].split():
                try:
                    ip = ipaddress.ip_address(value)
                    if not (ip.is_unspecified or ip.is_multicast):
                        result.append(str(ip))
                except ValueError:
                    pass
    return list(dict.fromkeys(result))


def main():
    interface = 'wlan0'
    config = Path(os.environ.get('FERMAX_CONFIG','/etc/fermax-gateway/config.json'))
    if config.exists():
        interface = json.loads(config.read_text())['home_interface']
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,15}',interface):
        raise ValueError('Invalid home interface')
    if len(sys.argv) > 1 and sys.argv[1] != interface:
        return
    options = subprocess.check_output(['nmcli', '-f', 'DHCP4.OPTION', 'device', 'show', interface], text=True, timeout=8)
    lease = servers(options)
    selected = lease or PUBLIC
    path = Path('/run/systemd/timesyncd.conf.d/70-fermax-dhcp.conf')
    path.parent.mkdir(parents=True, exist_ok=True)
    content = '[Time]\nNTP=\nNTP='+' '.join(selected)+'\nFallbackNTP='+' '.join(PUBLIC)+'\n'
    if not path.exists() or path.read_text() != content:
        temp = path.with_suffix('.new')
        temp.write_text(content)
        os.replace(temp, path)
        subprocess.run(['systemctl', 'try-restart', 'systemd-timesyncd.service'], check=True, timeout=10)
    Path('/run/fermax-ntp.json').write_text(json.dumps({'source':'dhcp' if lease else 'public', 'servers':selected}))


if __name__ == '__main__':
    main()
