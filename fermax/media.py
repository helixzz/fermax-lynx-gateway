"""Decode the observed encrypted RTP/H.264 profile into live JPEG frames."""
import io
import logging
import queue
import struct
import threading
import time


class Video:
    def __init__(self, codec, state):
        self.codec, self.state = codec, state
        self.queue = queue.Queue(maxsize=256)
        self.stop = threading.Event()
        self.generation = 0
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def reset(self):
        self.generation += 1
        with self.state.lock:
            self.state.video_jpeg = None

    def feed(self, packet):
        try:
            self.queue.put_nowait((self.generation, packet))
        except queue.Full:
            pass

    def run(self):
        import av
        context, source, seq, generation = None, None, None, None
        last_frame = 0
        while not self.stop.is_set():
            try:
                item_generation, packet = self.queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item_generation != self.generation:
                continue
            try:
                if len(packet) < 20 or packet[0] != 0x80 or packet[1] & 127 != 98:
                    continue
                current_seq, _, ssrc = struct.unpack_from('!HII', packet, 2)
                if source != ssrc or generation != item_generation:
                    context = av.CodecContext.create('h264', 'r')
                    context.thread_count = 1
                    source, generation, seq = ssrc, item_generation, None
                data = self.codec.decrypt(packet[12:])
                if not data or data[0] & 31 not in (1,5,7,8):
                    continue
                seq = current_seq
                nal = b'\x00\x00\x00\x01'+bytes([data[0]&127])+data[1:]
                for parsed in context.parse(nal):
                    for frame in context.decode(parsed):
                        now = time.monotonic()
                        if now-last_frame >= 0.25:
                            image = frame.to_image()
                            output = io.BytesIO()
                            image.save(output, format='JPEG', quality=72)
                            with self.state.lock:
                                if item_generation == self.generation:
                                    self.state.video_jpeg = output.getvalue()
                                    self.state.video_updated = self.state.mono()
                            last_frame = now
            except Exception:
                # A stream may start between keyframes; continue until decodable.
                continue
