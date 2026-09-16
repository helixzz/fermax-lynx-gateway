import tempfile
import unittest
from pathlib import Path
from fermax.diagnostics import Diagnostics


class DiagnosticTests(unittest.TestCase):
    def test_bounded_persistent_and_rate_limited(self):
        with tempfile.TemporaryDirectory() as folder:
            now = [1000000.]
            d = Diagnostics(Path(folder), lambda:now[0])
            d.LIMIT = 3
            for i in range(5): d.record('synthetic', {'sequence':i})
            self.assertEqual([r['detail']['sequence'] for r in d.logs()], [4,3,2])
            self.assertTrue(d.record('client', rate_key='device'))
            self.assertFalse(d.record('client', rate_key='device'))
            self.assertEqual(len(d.logs(before=d.logs()[0]['id'])),2)
            now[0] += d.AGE+1
            self.assertEqual(d.logs(), [])
            self.assertTrue(d.record('new'))
            self.assertEqual(len(Diagnostics(Path(folder),lambda:now[0]).logs()),1)

    def test_bad_payload_does_not_break_call_processing(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Diagnostics(Path(folder))
            self.assertFalse(d.record('oversize', {'text':'x'*5000}))
            self.assertFalse(d.record('invalid', {'value':object()}))
            self.assertEqual(d.logs(),[])

    def test_corrupt_diagnostic_file_does_not_prevent_startup(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            (path/'diagnostics.sqlite3').write_bytes(b'not a database')
            d=Diagnostics(path)
            self.assertFalse(d.available)
            self.assertFalse(d.record('call'))
