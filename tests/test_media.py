"""Exercise RTP decryption and decoding with generated, non-private video."""
import importlib.util
import io
import re
import struct
import tempfile
import time
import unittest


@unittest.skipUnless(importlib.util.find_spec('av'),'Requires python3-av')
class MediaTests(unittest.TestCase):
    def test_synthetic_h264_encrypted_rtp_to_jpeg(self):
        import av
        from PIL import Image
        from fractions import Fraction
        from fermax.protocol import Codec
        from fermax.state import State
        from fermax.media import Video
        with tempfile.TemporaryDirectory() as folder:
            state=State(folder)
            wire=Codec(None,b'01234567ABCDEFGHabcdefgh')
            decoder=Video(wire,state)
            try:
                encoder=av.CodecContext.create('libx264','w')
                encoder.width,encoder.height,encoder.pix_fmt=320,240,'yuv420p'
                encoder.time_base=Fraction(1,15)
                encoder.options={'preset':'ultrafast','tune':'zerolatency','repeat-headers':'1'}
                packets=[]
                for i in range(25):
                    frame=av.VideoFrame.from_image(Image.new('RGB',(320,240),(210,30,20)))
                    frame.pts=i
                    packets.extend(encoder.encode(frame))
                packets.extend(encoder.encode(None))
                sequence=0
                for packet in packets:
                    for nal in re.split(b'\x00\x00\x00?\x01',bytes(packet)):
                        if not nal:continue
                        decoder.feed(struct.pack('!BBHII',0x80,98,sequence,sequence*6000,321)+wire.encrypt(nal))
                        sequence+=1
                    time.sleep(.02)
                deadline=time.monotonic()+8
                while state.video_jpeg is None and time.monotonic()<deadline:time.sleep(.05)
                self.assertIsNotNone(state.video_jpeg)
                image=Image.open(io.BytesIO(state.video_jpeg))
                self.assertEqual(image.size,(320,240))
                red,green,blue=image.getpixel((160,120))
                self.assertGreater(red,180);self.assertLess(green,60);self.assertLess(blue,60)
                decoder.reset()
                self.assertIsNone(state.video_jpeg)
            finally:
                decoder.stop.set();decoder.thread.join(2);state.db.close()
