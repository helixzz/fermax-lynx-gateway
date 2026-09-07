/* Cosmetic preferences only: no credentials in browser storage. */
(() => {
  'use strict';
  const key = 'lynx-phone-display-v1', styles = ['editorial','digital','analog','nixie'], seconds = ['hidden','step','sweep'];
  class LynxClock {
    constructor() {
      this.value = {style:'editorial',seconds:'hidden',volume:35};
      try { const saved = JSON.parse(localStorage.getItem(key)); if (saved) this.value = Object.assign(this.value,saved); } catch (_) {}
      if (!styles.includes(this.value.style)) this.value.style = 'editorial';
      if (!seconds.includes(this.value.seconds)) this.value.seconds = 'hidden';
      if (!Number.isFinite(this.value.volume) || this.value.volume < 0 || this.value.volume > 100) this.value.volume = 35;
      document.querySelector('#clockStyle').value = this.value.style;
      document.querySelector('#secondsMode').value = this.value.seconds;
      document.querySelector('#volume').value = this.value.volume;
      const dial = document.querySelector('#dialTicks'), ns = 'http://www.w3.org/2000/svg';
      for(let i=0;i<60;i++) { const tick = document.createElementNS(ns,'line');
        tick.setAttribute('x1','160'); tick.setAttribute('x2','160'); tick.setAttribute('y1',i%5 ? '23' : '18'); tick.setAttribute('y2',i%5 ? '28' : '34');
        tick.setAttribute('transform','rotate('+i*6+' 160 160)'); tick.setAttribute('class',i%5 ? 'minor-tick' : 'major-tick'); dial.append(tick); }
      this.apply();
    }
    apply() { document.body.dataset.clock = this.value.style; document.body.dataset.seconds = this.value.seconds; }
    save() { this.apply(); try { localStorage.setItem(key,JSON.stringify(this.value)); } catch (_) {} }
    update(date) {
      const pad = n => String(n).padStart(2,'0'), h = date.getUTCHours(), m = date.getUTCMinutes(), s = date.getUTCSeconds();
      const time = pad(h)+':'+pad(m), full = time+':'+pad(s);
      document.querySelector('#time').textContent = time;
      document.querySelector('#seconds').textContent = pad(s);
      document.querySelector('#clockFace').setAttribute('aria-label',this.value.seconds === 'hidden' ? time : full);
      const digits = document.querySelectorAll('.tube-digit');
      (pad(h)+pad(m)+pad(s)).split('').forEach((digit,i) => { if (digits[i].textContent !== digit) digits[i].textContent = digit; });
      const fraction = this.value.seconds === 'sweep' && !matchMedia('(prefers-reduced-motion: reduce)').matches ? date.getUTCMilliseconds()/1000 : 0;
      document.querySelector('#hourHand').style.transform = 'rotate('+((h%12)*30+m*.5+s/120)+'deg)';
      document.querySelector('#minuteHand').style.transform = 'rotate('+(m*6+s*.1)+'deg)';
      document.querySelector('#secondHand').style.transform = 'rotate('+((s+fraction)*6)+'deg)';
    }
  }
  window.LynxClock = LynxClock;
})();
