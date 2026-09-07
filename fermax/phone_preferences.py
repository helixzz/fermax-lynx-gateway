"""Administrator-owned ringtone settings; bounded PCM music stored outside source."""
import hashlib
import io
import json
import os
import threading
import wave

from .state import atomic_json

MAX_MUSIC_BYTES = 6 * 1024 * 1024
RINGTONES = ('chime', 'harbor', 'marimba', 'custom')
DURATIONS = (15, 30, 45, 60)


class PhonePreferences:
    def __init__(self, folder):
        self.folder = folder
        self.path = folder/'phone-preferences.json'
        self.music = folder/'phone-music'
        self.lock = threading.RLock()
        self.record_lock = threading.Lock()
        self.pinned_revision = None
        self.value = {'ringtone':'chime', 'ring_seconds':30, 'music_revision':None, 'music_name':None}
        if self.path.exists():
            saved = json.loads(self.path.read_text())
            self.validate(saved)
            revision = saved.get('music_revision')
            if revision is not None and (not isinstance(revision,str) or len(revision) != 64 or any(c not in '0123456789abcdef' for c in revision)):
                raise ValueError('Invalid stored ringtone revision')
            self.value.update({k:saved[k] for k in self.value if k in saved})

    @staticmethod
    def validate(value):
        if value.get('ringtone') not in RINGTONES:
            raise ValueError('请选择有效铃声')
        if type(value.get('ring_seconds')) is not int or value['ring_seconds'] not in DURATIONS:
            raise ValueError('响铃时长只能为 15、30、45 或 60 秒')

    def snapshot(self):
        # Writers replace this immutable record only after committing. State sampling
        # must never wait for an upload/fsync while holding the controller state lock.
        result = dict(self.value)
        result['custom_available'] = bool(result['music_revision'] and (self.music/(result['music_revision']+'.wav')).is_file())
        return result

    def capture_call(self):
        # This short lock never covers disk I/O. Pin a visit's music before a writer
        # publishes its replacement, so a refreshed phone can still load that track.
        with self.record_lock:
            self.pinned_revision = self.value['music_revision']
            return dict(self.value)

    def end_call(self):
        with self.record_lock:
            self.pinned_revision = None

    def update(self, value):
        self.validate(value)
        with self.lock:
            if value['ringtone'] == 'custom' and not self.snapshot()['custom_available']:
                raise ValueError('请先上传铃声音乐')
            updated = dict(self.value, ringtone=value['ringtone'], ring_seconds=value['ring_seconds'])
            atomic_json(self.path, updated)
            with self.record_lock:
                self.value = updated
            return self.snapshot()

    def upload(self, data):
        if not 0 < len(data) <= MAX_MUSIC_BYTES:
            raise ValueError('铃声文件过大')
        try:
            with wave.open(io.BytesIO(data),'rb') as source:
                channels, rate, width, frames = source.getnchannels(), source.getframerate(), source.getsampwidth(), source.getnframes()
                if channels not in (1,2) or width != 2 or not 8000 <= rate <= 48000 or not 0 < frames <= rate*60 or source.getcomptype() != 'NONE':
                    raise ValueError('需要不超过 60 秒的 16-bit PCM WAV 音乐')
                pcm = source.readframes(frames)
                if len(pcm) != frames*channels*width:
                    raise ValueError('铃声文件不完整')
            # Re-encode the allowed PCM only, dropping uploaded metadata/trailing bytes.
            output = io.BytesIO()
            with wave.open(output,'wb') as target:
                target.setnchannels(channels); target.setsampwidth(width); target.setframerate(rate); target.writeframes(pcm)
            clean = output.getvalue()
        except (wave.Error, EOFError) as error:
            raise ValueError('无法读取铃声，请在管理页选择有效音频') from error
        revision = hashlib.sha256(clean).hexdigest()
        with self.lock:
            self.music.mkdir(mode=0o700,exist_ok=True)
            path = self.music/(revision+'.wav')
            temp = path.with_suffix('.new')
            try:
                with temp.open('wb') as stream:
                    os.chmod(temp,0o600); stream.write(clean); stream.flush(); os.fsync(stream.fileno())
                os.replace(temp,path)
                updated = dict(self.value, music_revision=revision, music_name='自定义音乐')
                atomic_json(self.path,updated)
                with self.record_lock:
                    self.value = updated
                    keep = {revision, self.pinned_revision}
            except BaseException:
                if revision != self.value['music_revision']: path.unlink(missing_ok=True)
                raise
            finally:
                temp.unlink(missing_ok=True)
            for old in self.music.glob('*.wav'):
                if old.stem not in keep: old.unlink(missing_ok=True)
            return self.snapshot()

    def audio(self, revision=None):
        with self.lock:
            current = self.value['music_revision']
            revision = revision or current
            if not revision or revision not in (current,self.pinned_revision):
                return None
            try: return (self.music/(revision+'.wav')).read_bytes()
            except FileNotFoundError: return None
