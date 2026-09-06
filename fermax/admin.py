"""Local recovery: python -m fermax.admin init|password|config|api-token."""
import argparse
import getpass
import json
import os
import secrets
import sys
from pathlib import Path
from . import config
from .auth import set_password
from .state import atomic_json


def write_token(folder):
    path = folder/'api-token'
    fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:
        os.chmod(path,0o600)
        f.write(secrets.token_urlsafe(32))
        f.flush()
        os.fsync(f.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',type=Path,default=Path.home()/'.local/state/fermax')
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init')
    sub.add_parser('password').add_argument('--stdin',action='store_true',help='Read password from stdin; do not put secrets in shell arguments')
    sub.add_parser('config').add_argument('--file',type=Path)
    sub.add_parser('api-token')
    args = parser.parse_args()
    folder = args.state_dir
    folder.mkdir(parents=True,exist_ok=True)
    try:
        if args.command=='init':
            path = folder/'config.json'
            if not path.exists():
                atomic_json(path,config.EXAMPLE)
            print('Example configuration: '+str(path))
            print('Edit site addresses, install your own key as edk, then run password before starting.')
        elif args.command=='password':
            password = sys.stdin.readline().rstrip('\r\n') if args.stdin else getpass.getpass('New password: ')
            if not args.stdin and password!=getpass.getpass('Repeat password: '):
                raise ValueError('Passwords do not match')
            set_password(folder,password)
            print('Password reset; existing web sessions revoked. No restart required.')
        elif args.command=='api-token':
            write_token(folder)
            print('New API token written to '+str(folder/'api-token')+'; previous token revoked.')
        elif args.command=='config':
            if args.file:
                atomic_json(folder/'config.json',config.load(args.file))
                print('Configuration saved. Configure the OS interface address and restart the gateway to apply.')
            else:
                print(json.dumps(config.load(folder/'config.json'),ensure_ascii=False,indent=2))
    except (ValueError,OSError) as error:
        parser.exit(2,str(error)+'\n')


if __name__=='__main__':
    main()
