"""Independent, bounded gateway ringing. Hardware I/O only starts explicitly in main."""
import array
import hashlib
import io
import json
import logging
import math
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import wave
from functools import lru_cache
from pathlib import Path

from .state import atomic_json


def outputs(proc=Path('/proc/asound'), sys_sound=Path('/sys/class/sound')):
    """Enumerate hardware playback PCMs only; never open a stream to discover it."""
    devices = []
    for card in proc.glob('card[0-9]*'):
        try:
            card_id = (card/'id').read_text().strip()
            if not re.fullmatch(r'[A-Za-z0-9_]+', card_id):
                continue
            physical = (sys_sound/card.name/'device').resolve()
            usb = next((p for p in (physical, *physical.parents) if (p/'idVendor').is_file()), None)
            identity = str(physical).split('/sound/')[0]
            if usb:
                serial = (usb/'serial').read_text().strip() if (usb/'serial').exists() else ''
                if serial:
                    interface = (physical/'bInterfaceNumber').read_text().strip() if (physical/'bInterfaceNumber').exists() else ''
                    identity = ':'.join([(usb/'idVendor').read_text().strip(), (usb/'idProduct').read_text().strip(), serial, interface])
            for pcm in card.glob('pcm*p'):
                number = re.fullmatch(r'pcm([0-9]+)p', pcm.name)
                if not number:
                    continue
                fields = dict(line.split(':', 1) for line in (pcm/'info').read_text().splitlines() if ':' in line)
                name = fields.get('name', fields.get('id', card_id)).strip()
                descriptor = (card_id+' '+name).lower()
                kind = 'usb' if usb else 'hdmi' if 'hdmi' in descriptor or 'displayport' in descriptor else 'analog' if any(x in descriptor for x in ('headphone','analog','bcm2835')) else 'other'
                stable = hashlib.sha256((identity+':pcm'+number[1]).encode()).hexdigest()
                devices.append({'id':stable, 'name':card_id+' · '+name, 'kind':kind,
                                'pcm':'plughw:CARD='+card_id+',DEV='+number[1]})
        except (OSError, ValueError):
            # Hot removal during enumeration is expected.
            continue
    return sorted(devices, key=lambda d: ({'usb':0,'analog':1,'hdmi':2,'other':3}[d['kind']],d['id']))


def candidates(devices, preferred):
    automatic = sorted((d for d in devices if d['id']!=preferred and d['kind'] in ('usb','analog','hdmi')),key=lambda d:({'usb':0,'analog':1,'hdmi':2}[d['kind']],d['id']))
    return [d for d in devices if d['id']==preferred] + automatic


@lru_cache(maxsize=2)
def builtin(tone):
    """Same score and oscillator envelopes as the browser; render off the SIP thread."""
    from .phone_preferences import CATALOG
    track = next(t for t in CATALOG if t['id']==tone)
    rate, beat = 24000, 60/track['bpm']
    samples = [0.] * math.ceil((sum(track['beats'])*beat+1.1)*rate)
    position = 0
    voice = track['voice']
    for note, beats in zip(track['notes'], track['beats']):
        frequency, start = 440*2**((note-69)/12), int(position*rate)
        duration = min(beats*beat+.45,1.4)
        for i in range(math.ceil(duration*rate)):
            if start+i>=len(samples): break
            t = i/rate
            phase = 2*math.pi*frequency*t
            slow = voice in ('soft','sine')
            envelope = min(1,t/(.025 if slow else .009))*math.exp(-t*(3.8 if slow else 6.5))*min(1,(duration-t)/.05)
            value = math.sin(phase)
            if voice in ('bell','glass'): value += .25*math.sin(phase*2.01)*math.exp(-t*8)+.12*math.sin(phase*3.98)*math.exp(-t*13)
            if voice=='wood': value += .3*math.sin(phase*3)*math.exp(-t*16)
            if voice=='piano': value += .3*math.sin(phase*2)*math.exp(-t*6)+.14*math.sin(phase*3)*math.exp(-t*10)
            if voice=='pluck': value += .23*math.sin(phase*2)+.1*math.sin(phase*4)*math.exp(-t*9)
            samples[start+i] += envelope*value
        position += beats*beat
    peak = max(map(abs,samples)) or 1
    pcm = array.array('h',(round(s*.26/peak*32767) for s in samples))
    if sys.byteorder!='little': pcm.byteswap()
    return pcm.tobytes(), rate, 1


class AlsaPlayer:
    def __init__(self):
        self.process = None
        self.source = None
        self.errors = None

    def start(self, device, pcm, rate, channels):
        self.stop()
        self.source = tempfile.TemporaryFile()
        self.errors = tempfile.TemporaryFile()
        self.source.write(pcm); self.source.seek(0)
        try:
            self.process = subprocess.Popen(['aplay','-q','-D',device['pcm'],'-t','raw','-f','S16_LE','-r',str(rate),'-c',str(channels)],stdin=self.source,stdout=subprocess.DEVNULL,stderr=self.errors)
        except BaseException:
            self.stop()
            raise

    def poll(self):
        return self.process.poll()

    def stop(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=.25)
                except subprocess.TimeoutExpired:
                    self.process.kill(); self.process.wait(timeout=.25)
            self.process = None
        for stream in (self.source,self.errors):
            if stream: stream.close()
        self.source = self.errors = None


class GatewayAudio:
    def __init__(self, folder, music, mono=time.monotonic, discover=outputs, player=None):
        self.path = Path(folder)/'gateway-audio.json'
        self.music, self.mono, self.discover = music, mono, discover
        self.player = player or AlsaPlayer()
        self.guard, self.writer = threading.RLock(), threading.Lock()
        self.value = {'enabled':True,'volume':50,'output':'auto'}
        config_error = False
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text()); self.validate(saved); self.value = saved
            except (ValueError,TypeError,OSError):
                self.value['enabled'] = False
                config_error = True
        self.devices = []
        self.desired = None
        self.last_call = None
        self.config_error = config_error
        self.status = '声音配置损坏，已暂停响铃，请重新保存' if config_error else '等待音频服务启动'
        self.actual = None
        self.faults = {}
        self.stopping, self.wake = threading.Event(), threading.Event()
        self.thread = None

    @staticmethod
    def validate(value):
        if set(value)!= {'enabled','volume','output'} or type(value['enabled']) is not bool or type(value['volume']) is not int or not 0<=value['volume']<=100:
            raise ValueError('需要有效的响铃开关、0–100 音量和输出设备')
        if not isinstance(value['output'],str) or not (value['output']=='auto' or re.fullmatch('[0-9a-f]{64}',value['output'])):
            raise ValueError('请选择有效音频输出')

    def snapshot(self):
        with self.guard:
            return {'settings':dict(self.value),'devices':[{k:v for k,v in d.items() if k!='pcm'} | {'status':self.faults.get(d['id'],'已检测，待播放验证')} for d in self.devices],
                    'actual':self.actual,'status':self.status,'testing':bool(self.desired and self.desired['test'])}

    def update(self, value):
        self.validate(value)
        with self.writer:
            atomic_json(self.path,value)
            with self.guard:
                if self.config_error: self.status='声音设置已恢复，等待下一次来访'
                self.config_error = False
                previous = self.value
                self.value = dict(value)
                if not value['enabled']: self.status='网关响铃已关闭'
                elif not previous['enabled']: self.status='待机 · 下一次呼入自动响铃'
                # Changes never start/restart an existing visit. Disable stops immediately.
                if not value['enabled'] and self.desired:
                    self.desired = None
                if previous != value: self.wake.set()
        return self.snapshot()

    def call(self, call_id, settings, started):
        with self.guard:
            if call_id==self.last_call: return
            self.last_call = call_id
            self.desired = None
            if self.value['enabled']:
                self.desired = {'id':call_id,'music':dict(settings),'deadline':started+settings['ring_seconds'],'test':False,'settings':dict(self.value)}
            self.wake.set()

    def end(self):
        with self.guard:
            self.desired = None
            self.wake.set()

    def test(self, stop=False):
        with self.guard:
            if stop:
                if self.desired and self.desired['test']: self.desired = None
            else:
                if self.desired and not self.desired['test']: raise ValueError('来访期间不能测试声音')
                if not self.value['enabled']: raise ValueError('请先启用网关响铃')
                if self.desired: raise ValueError('正在测试，请先停止')
                # Test a short original chime: no music file pin or private media dependency.
                self.desired = {'id':uuid.uuid4().hex,'music':{'ringtone':'chime'},'deadline':self.mono()+3,'test':True,'settings':dict(self.value)}
            self.wake.set()
        return self.snapshot()

    def start(self):
        if self.thread: return
        self.thread = threading.Thread(target=self.run,name='gateway-audio',daemon=True)
        self.thread.start()

    def close(self):
        self.stopping.set(); self.wake.set()
        if self.thread: self.thread.join(timeout=5)

    def live(self, job):
        with self.guard:
            return not self.stopping.is_set() and self.desired is job and self.value['enabled'] and self.mono()<job['deadline']

    def phrase(self, music):
        if music['ringtone']!='custom': return builtin(music['ringtone'])
        data = self.music.audio(music['music_revision'])
        if not data: raise ValueError('自定义音乐不可用')
        with wave.open(io.BytesIO(data),'rb') as source:
            return source.readframes(source.getnframes()), source.getframerate(), source.getnchannels()

    def scan(self):
        devices = self.discover()
        with self.guard:
            self.devices = devices
        return devices

    def play(self, job):
        tried = set()
        pcm,rate,channels = self.phrase(job['music'])
        volume = job['settings']['volume']/100
        samples = array.array('h'); samples.frombytes(pcm)
        if sys.byteorder!='little': samples.byteswap()
        samples = array.array('h',(round(n*volume) for n in samples))
        if sys.byteorder!='little': samples.byteswap()
        pcm = samples.tobytes()
        while self.live(job):
            devices = candidates(self.scan(),job['settings']['output'])
            device = next((d for d in devices if d['id'] not in tried),None)
            if not device or len(tried)>=8: self.status='没有可用输出，请连接扬声器或检查权限/占用'; return
            tried.add(device['id'])
            # Bounded input; process deadline also enforces time spent opening/draining.
            size = max(0,int((job['deadline']-self.mono())*rate))*channels*2
            if not size or not self.live(job): return
            payload = (pcm*(size//len(pcm)+1))[:size]
            try:
                self.player.start(device,payload,rate,channels)
                self.actual = {k:v for k,v in device.items() if k!='pcm'}
                self.status = ('测试声音' if job['test'] else '呼入响铃')+' · '+device['name']
                if len(tried)>1 or (job['settings']['output']!='auto' and device['id']!=job['settings']['output']): self.status += '（已降级）'
                with self.guard: self.faults[device['id']]='播放已启动，请确认实际声音'
                next_check=self.mono()+.5
                while self.live(job) and self.player.poll() is None:
                    if self.mono()>=next_check:
                        if not any(d['id']==device['id'] for d in self.scan()): break
                        next_check=self.mono()+.5
                    self.wake.wait(.05); self.wake.clear()
                if not self.live(job): return
                with self.guard: self.faults[device['id']]='播放结束过早：检查连接、权限或设备占用'
                logging.warning('Gateway audio output ended early or disconnected (%s)',device['kind'])
            except OSError:
                with self.guard: self.faults[device['id']]='无法启动播放：检查 alsa-utils、权限或设备占用'
                logging.warning('Gateway audio output unavailable (%s)',device['kind'])
            finally:
                self.player.stop(); self.actual = None

    def run(self):
        next_scan = 0
        handled = None
        try:
            while not self.stopping.is_set():
                if self.mono()>=next_scan:
                    try:
                        self.scan()
                        if not self.desired and not self.config_error:
                            if not self.value['enabled']: self.status='网关响铃已关闭'
                            elif not self.devices: self.status='未检测到音频输出，连接扬声器后再测试'
                            elif self.status.startswith(('等待','网关响铃已关闭','未检测到','呼入响铃','测试声音')): self.status='待机 · 下一次呼入自动响铃'
                    except OSError: self.status='无法读取音频设备'
                    next_scan = self.mono()+3
                with self.guard: job = self.desired
                if job and job is not handled:
                    handled = job
                    try: self.play(job)
                    except Exception:
                        self.status='音乐播放失败，请检查音频设置'
                        logging.warning('Gateway ringtone could not be prepared or played')
                    finally:
                        with self.guard:
                            if self.desired is job: self.desired = None
                self.wake.wait(.05); self.wake.clear()
        finally: self.player.stop()
