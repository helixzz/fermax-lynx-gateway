/* Local, bounded ringtone playback. No microphone or external music URLs. */
(() => {
  'use strict';
  class LynxSound {
    constructor() { this.context = null; this.source = null; this.gain = null; this.ticket = 0; this.cache = new Map(); this.mode = null; }
    async enable() {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) throw Error('浏览器不支持铃声播放');
      if (!this.context) this.context = new Audio();
      await this.context.resume();
      if (this.context.state !== 'running') throw Error('请再次轻触启用铃声，并检查系统静音设置');
    }
    get enabled() { return this.context && this.context.state === 'running'; }
    stop() {
      this.ticket++;
      if (this.source) { try { this.source.stop(); } catch (_) {} this.source.disconnect(); }
      if (this.gain) this.gain.disconnect();
      this.source = this.gain = null; this.mode = null;
    }
    volume(value) { if (this.gain) this.gain.gain.value = Math.max(0,Math.min(1,value)); }
    builtin(name) {
      const melodies = {chime:[659.25,523.25,783.99,659.25], harbor:[392,523.25,587.33,783.99,587.33,523.25], marimba:[523.25,659.25,783.99,1046.5,783.99,659.25]};
      const notes = melodies[name] || melodies.chime, rate = 24000, spacing = name === 'chime' ? .48 : .38;
      const buffer = this.context.createBuffer(1,Math.ceil((notes.length*spacing+1.2)*rate),rate), samples = buffer.getChannelData(0);
      notes.forEach((frequency,index) => {
        const start = Math.floor(index*spacing*rate);
        for (let i = 0; i < rate*.7 && start+i < samples.length; i++) {
          const t = i/rate, envelope = Math.min(1,t/.012)*Math.exp(-t*7);
          samples[start+i] += .23*envelope*(Math.sin(2*Math.PI*frequency*t)+.2*Math.sin(2*Math.PI*frequency*2*t));
        }
      });
      return buffer;
    }
    async prepare(settings, endpoint='/v1/phone/ringtone') {
      if (!this.context) return null;
      const key = settings.ringtone === 'custom' ? settings.music_revision : settings.ringtone;
      if (this.cache.has(key)) return this.cache.get(key);
      let buffer;
      if (settings.ringtone === 'custom') {
        if (!settings.music_revision) throw Error('管理员尚未上传铃声音乐');
        const abort = new AbortController(), timeout = setTimeout(() => abort.abort(),8000);
        try {
          const response = await fetch(endpoint+'?revision='+encodeURIComponent(settings.music_revision),{cache:'no-store',signal:abort.signal});
          if (!response.ok) throw Error('自定义铃声暂不可用');
          buffer = await this.context.decodeAudioData(await response.arrayBuffer());
          if (!buffer.duration || buffer.duration > 60.1) throw Error('铃声不能超过 60 秒');
        } finally { clearTimeout(timeout); }
      } else buffer = this.builtin(settings.ringtone);
      if (this.cache.size >= 2) this.cache.delete(this.cache.keys().next().value);
      this.cache.set(key,buffer); return buffer;
    }
    async play(settings, seconds, volume, mode='call', endpoint='/v1/phone/ringtone') {
      this.stop(); const ticket = this.ticket, started = performance.now();
      if (!this.enabled || seconds <= 0) return;
      this.mode = mode;
      let buffer;
      try { buffer = await this.prepare(settings,endpoint); }
      catch (error) { if (ticket !== this.ticket) return; this.mode = null; throw error; }
      const remaining = seconds-(performance.now()-started)/1000;
      if (ticket !== this.ticket || !this.enabled || remaining <= 0) { if (ticket === this.ticket) this.mode = null; return; }
      const source = this.context.createBufferSource(), gain = this.context.createGain();
      source.buffer = buffer; source.loop = true; gain.gain.value = volume;
      source.connect(gain); gain.connect(this.context.destination);
      this.source = source; this.gain = gain; this.mode = mode;
      source.onended = () => { source.disconnect(); gain.disconnect(); if (this.source === source) { this.source = this.gain = null; this.mode = null; } };
      source.start(); source.stop(this.context.currentTime+remaining);
    }
    async importMusic(file) {
      if (!file || file.size > 10*1024*1024) throw Error('请选择不超过 10 MB 的音频文件');
      await this.enable();
      const decoded = await this.context.decodeAudioData(await file.arrayBuffer());
      if (!(decoded.duration > 0 && decoded.duration <= 60)) throw Error('音乐最长 60 秒，请先截取喜欢的片段');
      const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
      if (!Offline) throw Error('此浏览器不支持音频导入，请用较新的管理浏览器上传');
      const rate = 24000, offline = new Offline(1,Math.ceil(decoded.duration*rate),rate);
      const source = offline.createBufferSource(); source.buffer = decoded; source.connect(offline.destination); source.start();
      const rendered = await offline.startRendering(), pcm = rendered.getChannelData(0);
      const data = new ArrayBuffer(44+pcm.length*2), view = new DataView(data);
      const text = (offset,value) => { for(let i=0;i<value.length;i++) view.setUint8(offset+i,value.charCodeAt(i)); };
      text(0,'RIFF'); view.setUint32(4,36+pcm.length*2,true); text(8,'WAVE'); text(12,'fmt ');
      view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true);
      view.setUint32(24,rate,true); view.setUint32(28,rate*2,true); view.setUint16(32,2,true); view.setUint16(34,16,true);
      text(36,'data'); view.setUint32(40,pcm.length*2,true);
      for(let i=0;i<pcm.length;i++) view.setInt16(44+i*2,Math.round(Math.max(-1,Math.min(1,pcm[i]))*32767),true);
      return data;
    }
  }
  window.LynxSound = LynxSound;
})();
