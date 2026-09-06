"""Wire codecs and an observational SIP reducer; no network transmission."""
import base64
import uuid
from dataclasses import dataclass, field
from pathlib import Path

try:
    from Crypto.Cipher import DES3
    from Crypto.Util.Padding import pad, unpad
except ImportError:
    from Cryptodome.Cipher import DES3
    from Cryptodome.Util.Padding import pad, unpad
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory, json_format


class Codec:
    def __init__(self, schema, key):
        if len(key) != 24:
            raise ValueError('Expected a 24-byte key')
        self.key = key
        if schema is None:
            from .schema import files as wire_files
            files = wire_files()
        else:
            files = list(descriptor_pb2.FileDescriptorSet.FromString(Path(schema).read_bytes()).file)
        pool = descriptor_pool.DescriptorPool()
        loaded = set()
        while files:
            ready = [f for f in files if set(f.dependency) <= loaded]
            if not ready:
                raise ValueError('Unresolved schema dependencies')
            for f in ready:
                pool.Add(f)
                loaded.add(f.name)
                files.remove(f)
        desc = pool.FindMessageTypeByName('protobuffers.Message')
        if hasattr(message_factory, 'GetMessageClass'):
            self.message = message_factory.GetMessageClass(desc)
        else:
            # Debian's protobuf 3.x requires explicit extension registration.
            self.message = message_factory.MessageFactory(pool).GetMessages(list(loaded))[desc.full_name]

    def encrypt(self, clear):
        return DES3.new(self.key, DES3.MODE_ECB).encrypt(pad(clear, 8))

    def decrypt(self, data):
        if not data or len(data) % 8:
            raise ValueError('Invalid ciphertext length')
        return unpad(DES3.new(self.key, DES3.MODE_ECB).decrypt(data), 8)

    def decode(self, clear):
        msg = self.message.FromString(clear)
        if not msg.IsInitialized():
            raise ValueError('Missing required protobuf fields')
        return json_format.MessageToDict(msg, preserving_proto_field_name=True)

    def command(self, name, fields, message_id=None):
        return self.envelope('command', name, fields, message_id)

    def envelope(self, kind, name, fields, message_id=None):
        if kind not in ('command', 'response', 'event'):
            raise ValueError('Unknown envelope type')
        value = {'uuid': base64.b64encode(message_id or uuid.uuid4().bytes).decode(),
                 f'[protobuffers.{kind}]': {f'[protobuffers.{name}]': fields}}
        msg = json_format.ParseDict(value, self.message())
        return msg.SerializeToString()


@dataclass
class SIP:
    first: str
    headers: dict
    body: str

    @classmethod
    def parse(cls, wire):
        if isinstance(wire, str):
            wire = wire.encode()
        if len(wire) > 65535 or b'\r\n\r\n' not in wire:
            raise ValueError('Invalid SIP framing')
        head, body = wire.split(b'\r\n\r\n', 1)
        lines = head.decode('utf-8').split('\r\n')
        headers = {}
        for line in lines[1:]:
            if ':' not in line:
                raise ValueError('Invalid SIP header')
            name, value = line.split(':', 1)
            name = {'i':'call-id', 'l':'content-length'}.get(name.lower(), name.lower())
            if name in headers and name in ('call-id', 'cseq', 'content-length'):
                raise ValueError('Duplicate SIP identity header')
            headers[name] = value.strip()
        for key in ('call-id', 'cseq'):
            if key not in headers:
                raise ValueError('Missing SIP identity')
        length = int(headers.get('content-length', len(body)))
        if length < 0 or len(body) < length:
            raise ValueError('Truncated SIP body')
        return cls(lines[0], headers, body[:length].decode('utf-8'))

    @property
    def audio_port(self):
        for line in self.body.splitlines():
            if line.startswith('m=audio '):
                return int(line.split()[1])
        return None


@dataclass
class Call:
    call_id: str
    direction: str
    phase: str = 'ringing'
    pending_audio: dict = field(default_factory=dict)
    audio_port: int = 0


class Sessions:
    """Reduce archived SIP, distinguishing early video from accepted audio.

    Not a SIP transaction layer. Does not emit ACKs, retries, or responses.
    """
    def __init__(self, own):
        self.own = own
        self.calls = {}

    def feed(self, wire, source):
        sip = SIP.parse(wire)
        call_id = sip.headers['call-id']
        method = sip.first.split()[0]
        seq, cseq_method = sip.headers['cseq'].split()
        key = (source, seq)
        if method == 'INVITE' and call_id not in self.calls:
            self.calls[call_id] = Call(call_id, 'outgoing' if source == self.own else 'incoming')
        call = self.calls.get(call_id)
        if call is None or call.phase == 'ended':
            return call
        if method == 'INVITE':
            call.pending_audio[key] = sip.audio_port or 0
        elif method == 'SIP/2.0' and cseq_method == 'INVITE':
            status = int(sip.first.split()[1])
            # A response arrives from the opposite side of the transaction.
            pending = [k for k in call.pending_audio if k[1] == seq and k[0] != source]
            if 200 <= status < 300 and pending:
                offered = call.pending_audio.pop(pending[0])
                call.audio_port = sip.audio_port or 0
                call.phase = 'audio' if offered and call.audio_port else 'early_video'
            elif status >= 300 and pending:
                call.pending_audio.pop(pending[0])
                if call.phase == 'ringing':
                    call.phase = 'ended'
        elif method == 'BYE':
            call.phase = 'ended'
        elif method == 'CANCEL' and call.phase == 'ringing':
            call.phase = 'ended'
        return call
