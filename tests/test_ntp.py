import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('ntp_config', Path(__file__).resolve().parents[1]/'deploy/ntp.py')
ntp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ntp)


class NTPTests(unittest.TestCase):
    def test_only_option_42_is_used(self):
        text = 'DHCP4.OPTION[8]: ntp_servers = 192.0.2.123\nDHCP4.OPTION[9]: routers = 192.0.2.1\nDHCP4.OPTION[10]: subnet_mask = 255.255.255.0'
        self.assertEqual(ntp.servers(text), ['192.0.2.123'])

    def test_missing_invalid_servers_use_public_fallback(self):
        for value in ('','requested_ntp_servers = 1','ntp_servers = invalid 0.0.0.0 224.0.0.1'):
            self.assertEqual(ntp.servers(value), [])
            self.assertEqual(ntp.servers(value) or ntp.PUBLIC, ntp.PUBLIC)
