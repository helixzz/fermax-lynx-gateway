"""Synthetic framebuffer rendering and touches; no framebuffer or input devices."""
import tempfile
import unittest
from pathlib import Path
from fermax.display import Display
from fermax.state import State
from tests.test_gateway_audio import USB, ANALOG


class AudioDisplayTests(unittest.TestCase):
    def test_sound_controls_share_persistence_and_do_not_touch_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);state=State(folder)
            # Use the same renderer with portable fonts in CI; local demos use the real fonts.
            from PIL import Image, ImageDraw, ImageFont
            import threading
            display=Display.__new__(Display)
            display.Image,display.Draw=Image,ImageDraw
            display.font=display.big=ImageFont.load_default()
            display.state=state;display.guard=threading.Lock();display.coeff=[[1,0,0],[0,1,0]]
            display.page='settings';display.selection=0;display.audio_offset=0
            display.path=folder/'touch.json'
            state.gateway_audio.devices=[USB,ANALOG]
            try:
                before=state.snapshot()['auto']
                display.press((40,120));self.assertEqual(display.page,'sound')
                display.press((40,120));self.assertFalse(state.gateway_audio.value['enabled'])
                display.press((40,120));self.assertTrue(state.gateway_audio.value['enabled'])
                display.press((400,160));self.assertEqual(state.gateway_audio.value['volume'],55)
                display.press((40,215));self.assertEqual(display.page,'outputs')
                display.press((40,165));self.assertEqual(state.gateway_audio.value['output'],USB['id'])
                display.press((40,285));self.assertTrue(state.gateway_audio.snapshot()['testing'])
                display.press((200,285));self.assertFalse(state.gateway_audio.snapshot()['testing'])
                self.assertEqual(state.snapshot()['auto'],before)
                import json
                self.assertEqual(json.loads((folder/'gateway-audio.json').read_text()),state.gateway_audio.value)
            finally: state.db.close()
