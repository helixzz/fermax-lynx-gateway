"""Ringtone persistence, bounded PCM assets and monotonic incoming-call age."""
import io
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from fermax.phone_preferences import PhonePreferences
from fermax.state import State


def music(sample=b'\x00\x00', frames=8000):
    buffer = io.BytesIO()
    with wave.open(buffer,'wb') as target:
        target.setnchannels(1); target.setsampwidth(2); target.setframerate(8000)
        target.writeframes(sample*frames)
    return buffer.getvalue()


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name); self.settings = PhonePreferences(self.folder)

    def test_default_and_all_durations_persist_without_policy_changes(self):
        self.assertEqual(self.settings.snapshot()['ring_seconds'],30)
        self.assertEqual(self.settings.snapshot()['ringtone'],'chime')
        for seconds in (15,30,45,60):
            self.settings.update({'ringtone':'harbor','ring_seconds':seconds})
            self.assertEqual(PhonePreferences(self.folder).snapshot()['ring_seconds'],seconds)
        for seconds in (True,None,'30',0,16,61):
            with self.assertRaises(ValueError): self.settings.update({'ringtone':'chime','ring_seconds':seconds})
        with self.assertRaises(ValueError): self.settings.update({'ringtone':'https://example.com/music','ring_seconds':30})
        with self.assertRaises(ValueError): self.settings.update({'ringtone':'custom','ring_seconds':30})
        self.assertFalse((self.folder/'policy.json').exists())

    def test_music_is_private_bounded_and_replaced_without_metadata(self):
        first = self.settings.upload(music()+b'PRIVATE UPLOAD METADATA')
        self.assertTrue(first['custom_available'])
        self.assertNotIn(b'PRIVATE',self.settings.audio())
        self.assertEqual((self.settings.music/(first['music_revision']+'.wav')).stat().st_mode & 0o777,0o600)
        self.settings.update({'ringtone':'custom','ring_seconds':45})
        second = self.settings.upload(music(b'\x10\x00'))
        self.assertNotEqual(first['music_revision'],second['music_revision'])
        self.assertIsNone(self.settings.audio(first['music_revision']))
        self.assertEqual(len(list(self.settings.music.glob('*.wav'))),1)
        restored = PhonePreferences(self.folder)
        self.assertEqual(restored.snapshot()['ringtone'],'custom')
        self.assertEqual(restored.audio(),self.settings.audio())

    def test_active_call_music_is_pinned_through_upload_and_refresh(self):
        first=self.settings.upload(music())
        self.settings.update({'ringtone':'custom','ring_seconds':15})
        captured=self.settings.capture_call()
        self.settings.upload(music(b'\x30\x00'))
        self.settings.update({'ringtone':'marimba','ring_seconds':60})
        self.assertEqual(captured['ring_seconds'],15)
        self.assertIsNotNone(self.settings.audio(first['music_revision']))
        self.assertEqual(len(list(self.settings.music.glob('*.wav'))),2)
        self.settings.end_call()
        self.assertIsNone(self.settings.audio(first['music_revision']))
        self.settings.upload(music(b'\x40\x00'))
        self.assertEqual(len(list(self.settings.music.glob('*.wav'))),1)

    def test_invalid_truncated_and_overlong_audio_preserves_previous_music(self):
        self.settings.upload(music()); original=self.settings.snapshot()
        for value in (b'not wav',music()[:-100],music(frames=8000*61)):
            with self.assertRaises(ValueError): self.settings.upload(value)
            self.assertEqual(self.settings.snapshot(),original)

    def test_failed_settings_commit_keeps_previous_selection_and_asset(self):
        self.settings.upload(music()); before=self.settings.snapshot(); original=self.settings.audio()
        with patch('fermax.phone_preferences.atomic_json',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError): self.settings.upload(music(b'\x20\x00'))
        self.assertEqual(self.settings.snapshot(),before)
        self.assertEqual(PhonePreferences(self.folder).audio(),original)
        self.assertEqual(len(list(self.settings.music.glob('*.wav'))),1)

    def test_failed_reupload_preserves_pinned_existing_music(self):
        first = self.settings.upload(music())
        self.settings.update({'ringtone':'custom','ring_seconds':30})
        self.settings.capture_call()
        second = self.settings.upload(music(b'\x20\x00'))
        with patch('fermax.phone_preferences.atomic_json',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError): self.settings.upload(music())
        self.assertEqual(self.settings.snapshot()['music_revision'],second['music_revision'])
        self.assertEqual(self.settings.audio(first['music_revision']),music())
        self.assertEqual(len(list(self.settings.music.glob('*.wav'))),2)

    def test_call_age_survives_wall_clock_jumps_and_does_not_flood_stream(self):
        now=[100.]; wall=[1000.]
        state=State(self.folder,mono=lambda:now[0],wall=lambda:wall[0]);self.addCleanup(state.db.close)
        state.call_id='synthetic-call';state.panel_id='entrance';state.direction='incoming';state.call='ringing'
        state.event('Synthetic call','incoming')
        first=state.stream_snapshot(['entrance'])
        now[0]+=16; wall[0]-=300
        next_state=state.stream_snapshot(['entrance'])
        self.assertEqual(next_state['state']['call_age'],16)
        self.assertEqual(next_state['version'],first['version'])
        self.assertEqual(state.phone_snapshot(['other'])['call_age'],0)
        state.phone_preferences.update({'ringtone':'marimba','ring_seconds':60})
        changed=state.stream_snapshot(['entrance'])
        self.assertGreater(changed['version'],first['version'])
        self.assertEqual(changed['state']['phone_preferences']['ring_seconds'],60)
        self.assertEqual(changed['state']['ring_preferences']['ring_seconds'],30)
