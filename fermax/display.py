"""Small framebuffer UI with four-point verified resistive-touch calibration."""
import array
import json
import logging
import math
import select
import threading
import time
import io
from datetime import datetime
from pathlib import Path

from .state import DURATIONS, atomic_json

TARGETS = [(45, 55), (435, 55), (240, 270), (85, 235)]


def find_framebuffer(root=Path('/sys/class/graphics')):
    for fb in root.glob('fb[0-9]*'):
        if (fb/'name').read_text().strip() == 'fb_ili9486':
            if (fb/'virtual_size').read_text().strip() != '480,320' or (fb/'bits_per_pixel').read_text().strip() != '16':
                raise RuntimeError('LCD must use 480x320 RGB565')
            return '/dev/'+fb.name
    raise RuntimeError('ILI9486 framebuffer not ready')


def affine(samples):
    # Exact three-point affine transform; fourth point independently checks it.
    a, b, c = samples[:3]
    det = a[0]*(b[1]-c[1])+b[0]*(c[1]-a[1])+c[0]*(a[1]-b[1])
    if abs(det) < 10000:
        raise ValueError('Calibration points too close')
    out = []
    for axis in (0, 1):
        u, v, w = [p[axis] for p in TARGETS[:3]]
        out.append([(u*(b[1]-c[1])+v*(c[1]-a[1])+w*(a[1]-b[1]))/det,
                    (a[0]*(v-w)+b[0]*(w-u)+c[0]*(u-v))/det,
                    (a[0]*(b[1]*w-c[1]*v)+b[0]*(c[1]*u-a[1]*w)+c[0]*(a[1]*v-b[1]*u))/det])
    return out


def transform(coeff, point):
    return tuple(sum(a*b for a, b in zip(row, (*point, 1))) for row in coeff)


class Display:
    def __init__(self, state, folder, framebuffer=None, font_path=None):
        from PIL import Image, ImageDraw, ImageFont
        self.Image, self.Draw = Image, ImageDraw
        self.state = state
        self.fb = framebuffer or find_framebuffer()
        font_path = font_path or '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc'
        self.font = ImageFont.truetype(font_path, 19)
        self.big = ImageFont.truetype(font_path, 27)
        self.path = Path(folder)/'touch.json'
        self.guard = threading.Lock()
        self.coeff = None
        if self.path.exists():
            try:
                value = json.loads(self.path.read_text())
                assert len(value) == 2 and all(len(r) == 3 and all(math.isfinite(x) for x in r) for r in value)
                self.coeff = value
            except (ValueError, TypeError, AssertionError):
                logging.warning('Invalid touch calibration; calibrating again')
        self.samples = []
        self.hint = '请用触摸笔轻点十字，然后松开'
        self.touch_available = False
        self.selection = 0
        self.page = 'home'
        self.audio_offset = 0
        self.network = ''
        self.stopping = threading.Event()

    def press(self, point):
        with self.guard:
            if self.coeff is None:
                self.samples.append(point)
                if len(self.samples) == 4:
                    try:
                        coeff = affine(self.samples)
                        if math.dist(transform(coeff, self.samples[3]), TARGETS[3]) > 28:
                            raise ValueError('Verification target missed')
                        atomic_json(self.path, coeff)
                        self.coeff = coeff
                    except ValueError:
                        self.samples = []
                        self.hint = '校准偏差较大，请重新轻点十字'
                return
            x, y = transform(self.coeff, point)
            snap = self.state.snapshot()
            if not (0 <= x < 480 and 0 <= y < 320):
                return
            try:
                if self.page == 'policy':
                    if 100 <= y < 155:
                        if x < 240:
                            self.selection = (self.selection+1) % len(DURATIONS)
                        else:
                            self.state.set_auto(DURATIONS[self.selection])
                    elif 170 <= y < 225:
                        if x < 240:
                            self.state.set_auto(None)
                        else:
                            self.samples, self.coeff = [], None
                            self.path.unlink(missing_ok=True)
                    elif y >= 260:
                        self.page = 'home'
                elif self.page == 'settings':
                    if 100 <= y < 155: self.page = 'sound' if x < 240 else 'policy'
                    elif 170 <= y < 225:
                        if x < 240:
                            self.samples, self.coeff = [], None
                            self.path.unlink(missing_ok=True)
                        else: self.page = 'home'
                elif self.page == 'sound':
                    audio = self.state.gateway_audio
                    value = audio.snapshot()['settings']
                    if 100 <= y < 145:
                        value['enabled'] = not value['enabled']; audio.update(value)
                    elif 150 <= y < 195:
                        if x < 160 or x >= 320:
                            value['volume'] = max(0,min(100,value['volume']+(-5 if x<160 else 5))); audio.update(value)
                    elif 200 <= y < 245: self.page = 'outputs'; self.audio_offset = 0
                    elif y >= 260:
                        if x < 160:
                            with self.state.lock:
                                if self.state.call != 'idle': raise ValueError('来访期间不能测试声音')
                                audio.test()
                        elif x < 320: audio.test(stop=True)
                        else: self.page = 'settings'
                elif self.page == 'outputs':
                    audio = self.state.gateway_audio
                    devices = [{'id':'auto'}]+audio.snapshot()['devices']
                    if 100 <= y < 250:
                        index = self.audio_offset+(y-100)//50
                        if index < len(devices):
                            value=audio.snapshot()['settings']; value['output']=devices[index]['id']; audio.update(value); self.page='sound'
                    elif y>=260:
                        if x<160: self.audio_offset=max(0,self.audio_offset-3)
                        elif x<320 and self.audio_offset+3<len(devices): self.audio_offset+=3
                        elif x>=320: self.page='sound'
                elif 185 <= y < 240:
                    if x < 160:
                        self.state.control('preview', snap['panels'][0]['id'])
                    elif x < 320:
                        if len(snap['panels'])>1:
                            self.state.control('preview', snap['panels'][1]['id'])
                    else:
                        self.state.control('answer')
                elif y >= 254:
                    if x < 160:
                        self.state.control('open')
                    elif x < 320:
                        self.state.control('hangup')
                    else:
                        self.page = 'settings'
            except (ValueError,OSError) as error:
                self.state.event(str(error), 'control_rejected')

    def touches(self):
        from evdev import InputDevice, list_devices, ecodes
        device = None
        for path in list_devices():
            candidate = InputDevice(path)
            if 'ADS7846' in candidate.name:
                device = candidate
                break
            candidate.close()
        if device is None:
            logging.warning('No ADS7846 touch input found')
            return
        self.touch_available = True
        device.grab()
        x = y = None
        down = released = False
        points = []
        try:
            while not self.stopping.is_set():
                if not select.select([device.fd], [], [], 0.5)[0]:
                    continue
                for event in device.read():
                    if event.type == ecodes.EV_ABS:
                        if event.code == ecodes.ABS_X:
                            x = event.value
                        elif event.code == ecodes.ABS_Y:
                            y = event.value
                    elif event.type == ecodes.EV_KEY and event.code == ecodes.BTN_TOUCH:
                        if event.value:
                            down, points = True, []
                        else:
                            down, released = False, True
                    elif event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT:
                        if down and x is not None and y is not None:
                            points.append((x, y))
                            points = points[-12:]
                        if released:
                            released = False
                            if points:
                                self.press(tuple(sorted(p[i] for p in points)[len(points)//2] for i in (0, 1)))
        finally:
            device.ungrab()
            device.close()

    def render(self):
        image = self.Image.new('RGB', (480, 320), '#101b2b')
        d = self.Draw.Draw(image)
        def text(x, y, value, color='#eaf1fa', big=False):
            d.text((x, y), value, font=self.big if big else self.font, fill=color)
        with self.guard:
            if self.coeff is None:
                text(105, 105, '触摸校准  '+str(len(self.samples)+1)+'/4', big=True)
                text(40, 150, self.hint)
                if not self.touch_available:
                    text(110, 185, '正在等待触摸设备', '#ffc66d')
                x, y = TARGETS[len(self.samples)]
                d.ellipse((x-15, y-15, x+15, y+15), outline='#58dccc', width=2)
                d.line((x-23, y, x+23, y), fill='white', width=2)
                d.line((x, y-23, x, y+23), fill='white', width=2)
            else:
                s = self.state.snapshot()
                text(12, 8, s['identity']['unit'][:8]+' · 门禁', big=True)
                text(285, 8, datetime.fromtimestamp(s['time']).strftime('%H:%M:%S'), big=True)
                labels = {'idle':'等待来访', 'ringing':'正在连接', 'early_video':'视频已接通', 'audio':'通话中', 'ending':'正在挂断'}
                text(12, 45, labels[s['call']] if s['network']=='ready' else '门禁网线未连接')
                text(275, 45, '已对时' if s['clock']['synchronized'] else '时间未同步', '#8fa4bc')
                p = s['auto']
                label = '关闭' if not p['enabled'] else ('无时限' if p['minutes'] == 0 else str(p['minutes'])+' 分钟')
                text(12, 72, '自动开门：'+label, '#58dccc')
                def button(box, label, color='#243952'):
                    d.rounded_rectangle(box, radius=7, fill=color)
                    text(box[0]+10, box[1]+10, label)
                if self.page == 'policy':
                    minutes = DURATIONS[self.selection]
                    button((8,100,235,155), '时长：'+('无时限' if minutes==0 else f'{minutes} 分钟')+' ›')
                    button((245,100,472,155), '启用自动开门')
                    button((8,170,235,225), '关闭自动开门')
                    button((245,170,472,225), '重新校准触摸')
                    button((8,264,472,314), '返回')
                elif self.page == 'settings':
                    button((8,100,235,155), '声音与扬声器')
                    button((245,100,472,155), '自动开门设置')
                    button((8,170,235,225), '重新校准触摸')
                    button((245,170,472,225), '返回首页')
                elif self.page == 'sound':
                    audio=self.state.gateway_audio.snapshot(); value=audio['settings']
                    button((8,100,472,145), '网关呼入响铃：'+('开启 · 点击关闭' if value['enabled'] else '关闭 · 点击开启'))
                    button((8,150,155,195), '音量 −')
                    text(204,160,str(value['volume'])+'%')
                    button((322,150,472,195), '音量 +')
                    selected=next((d['name'] for d in audio['devices'] if d['id']==value['output']), '自动 USB → 模拟 → HDMI' if value['output']=='auto' else '首选设备失联 · 自动降级')
                    button((8,200,472,245), '输出：'+selected[:19]+' ›')
                    button((8,264,155,314), '测试 3 秒')
                    button((165,264,312,314), '停止测试')
                    button((322,264,472,314), '返回')
                    d.rectangle((0,38,479,96),fill='#101b2b')
                    text(12,42,(audio['actual']['name'] if audio['actual'] else '当前未播放')[:24], '#58dccc')
                    text(12,70,audio['status'][:24], '#8fa4bc')
                elif self.page == 'outputs':
                    audio=self.state.gateway_audio.snapshot()
                    devices=[{'id':'auto','name':'自动 · USB → 模拟 → HDMI'}]+audio['devices']
                    for offset,device in enumerate(devices[self.audio_offset:self.audio_offset+3]):
                        name=('✓ ' if device['id']==audio['settings']['output'] else '')+device['name']
                        button((8,100+50*offset,472,145+50*offset),name[:25])
                    button((8,264,155,314), '上一页')
                    button((165,264,312,314), '下一页')
                    button((322,264,472,314), '返回')
                else:
                    for index, event in enumerate(s['events'][:3]):
                        stamp = datetime.fromtimestamp(event['time']).strftime('%H:%M')
                        line = stamp+' '+event['text']
                        width = 305 if s['video_ready'] else 455
                        while d.textlength(line, font=self.font) > width:
                            line = line[:-2]+'…'
                        text(12, 104+24*index, line, '#b6c6da')
                    if s['video_ready']:
                        with self.state.lock:
                            jpeg = self.state.video_jpeg
                        if jpeg:
                            preview = self.Image.open(io.BytesIO(jpeg))
                            preview.thumbnail((144,108))
                            image.paste(preview,(328,70))
                    button((8,185,155,239), s['panels'][0]['name'][:7])
                    button((165,185,312,239), s['panels'][1]['name'][:7] if len(s['panels'])>1 else '未配置')
                    button((322,185,472,239), '接听', '#243952' if s['audio_available'] else '#17263a')
                    button((8,254,155,314), '开门', '#1b675d' if s['allow_open'] else '#17263a')
                    button((165,254,312,314), '挂断')
                    button((322,254,472,314), '设置')
        return image

    def run(self):
        threading.Thread(target=self.touches, daemon=True).start()
        previous = None
        last_draw = 0
        with open(self.fb, 'r+b', buffering=0) as fb:
            while not self.stopping.is_set():
                image = self.render()
                rgb = image.tobytes()
                if rgb != previous or time.monotonic()-last_draw >= 5:
                    pixels = array.array('H', (((r>>3)<<11)|((g>>2)<<5)|(b>>3) for r,g,b in zip(rgb[0::3],rgb[1::3],rgb[2::3])))
                    import sys
                    if sys.byteorder != 'little':
                        pixels.byteswap()
                    fb.seek(0)
                    fb.write(pixels.tobytes())
                    previous = rgb
                    last_draw = time.monotonic()
                self.stopping.wait(0.15)
