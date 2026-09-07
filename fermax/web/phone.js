/* Phone-only credentials stay in HttpOnly cookies. Never replay a control request. */
(() => {
  'use strict';
  const $ = selector => document.querySelector(selector);
  let state = null, online = false, stopped = false, generation = 0, stream = null;
  let retryTimer, renewTimer, hideTimer, attempt = 0, lastMessage = 0, cursor = '';
  let epoch = '', version = -1, wall = 0, sampledAt = 0, imageURL = null, frameBusy = false;
  let authorizationRetry = false;
  let lastAutoResult = 0;
  const sound = new window.LynxSound(), clock = new window.LynxClock();
  let mutedCall = null, currentCall = null, pending = null, wakeLock = null;
  let ringPlan = null, ringStartedFor = null, sweepFrame = null, lastSweep = 0, messageTimer;
  const ringNames = Object.assign({custom:'自定义音乐'},Object.fromEntries(window.LynxRingtones.map(track=>[track.id,track.name])));
  const eventNames = {incoming:'收到来访', outgoing:'查看门口机', call_ended:'来访结束',
    open_manual:'门口机确认开门', open_auto:'自动开门已确认', open_unknown:'开门结果未知',
    open_denied:'开门被拒绝', control_failed:'操作未完成'};

  function message(text, transient=false) { clearTimeout(messageTimer); $('#message').textContent = text; if (transient) messageTimer = setTimeout(() => { $('#message').textContent = ''; },4000); }
  async function request(path, data) {
    const abort = new AbortController(), timeout = setTimeout(() => abort.abort(), 10000);
    try {
      const response = await fetch(path, {method:data === undefined ? 'GET' : 'POST',
        headers:data === undefined ? {} : {'Content-Type':'application/json'},
        body:data === undefined ? undefined : JSON.stringify(data), signal:abort.signal, cache:'no-store'});
      const body = await response.json();
      if (!response.ok) { const error = Error(body.error || '连接失败'); error.status = response.status; throw error; }
      return body;
    } finally { clearTimeout(timeout); }
  }
  function clearPicture() {
    $('#picture').hidden = true; $('#picture').removeAttribute('src');
    if (imageURL) URL.revokeObjectURL(imageURL);
    imageURL = null;
  }
  function offline(text) {
    online = false; sound.stop(); ringStartedFor = null; document.body.classList.add('offline');
    $('#gatewayStatus').textContent = '○ '+text;
    clearPicture(); buttons();
    $('#pictureHint').hidden = false; $('#pictureHint').textContent = '连接已中断，等待恢复';
    if (pending) { message('连接中断，操作结果未知；不会自动重试。'); pending = null; }
  }
  function buttons() {
    const usable = online && state && state.network === 'ready' && !pending;
    $('#open').disabled = !(usable && state.allow_open && ['early_video','audio'].includes(state.call));
    $('#hangup').disabled = !(usable && state.call_id && ['ringing','early_video','audio'].includes(state.call));
    $('#mute').disabled = !(state && state.direction === 'incoming');
    document.querySelectorAll('#panels button').forEach(button => { button.disabled = !(usable && state.call === 'idle'); });
  }
  function showControls() {
    $('#controls').hidden = false; document.body.classList.remove('dim');
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => { if (state && state.call === 'idle') hideControls(); }, 20000);
  }
  function hideControls() { $('#controls').hidden = true; document.body.classList.add('dim'); }
  function clockDate() { return new Date(wall+(state.utc_offset || 0)*1000+performance.now()-sampledAt); }
  function smoothClock(timestamp) {
    if (document.hidden || !state || state.call_id || clock.value.style !== 'analog' || clock.value.seconds !== 'sweep' || matchMedia('(prefers-reduced-motion: reduce)').matches) { sweepFrame = null; return; }
    if (timestamp-lastSweep >= 80) { clock.update(clockDate()); lastSweep = timestamp; }
    sweepFrame = requestAnimationFrame(smoothClock);
  }
  function updateClock() {
    if (!wall) return;
    const now = clockDate(); clock.update(now);
    $('#date').textContent = now.toLocaleDateString('zh-CN', {timeZone:'UTC',month:'long',day:'numeric',weekday:'long'}) +
      (online && state && state.clock_synchronized ? '' : ' · 时间未同步');
    $('#callTime').textContent = now.toLocaleTimeString('zh-CN', {timeZone:'UTC',hour12:false});
    if (!sweepFrame && clock.value.style === 'analog' && clock.value.seconds === 'sweep') sweepFrame = requestAnimationFrame(smoothClock);
  }
  function render(body) {
    if (body.schema !== 1 || !body.state || typeof body.version !== 'number') throw Error('不支持的状态格式');
    if (body.epoch === epoch && body.version < version) return;
    epoch = body.epoch; version = body.version; cursor = body.event_id;
    state = body.state; wall = body.server_time*1000; sampledAt = performance.now();
    lastMessage = performance.now(); online = true; attempt = 0; authorizationRetry = false;
    $('#setup').hidden = true; $('#phone').hidden = false;
    document.body.classList.remove('offline');
    $('#gatewayStatus').textContent = '● 网关已连接';
    $('#networkStatus').textContent = state.network === 'ready' ? '● 门禁已连接' : '○ 门禁未就绪';
    $('#autoStatus').textContent = state.auto.enabled ? '◉ 自动开门 · '+(state.auto.minutes === 0 ? '无时限' : '已启用') : '○ 自动开门已关闭';
    const active = !!state.call_id;
    document.body.classList.toggle('in-call',active);
    const preferences = state.phone_preferences || {ringtone:'chime',ring_seconds:30};
    $('#ringSetting').textContent = (ringNames[preferences.ringtone] || '清脆门铃')+' · 最长响铃 '+preferences.ring_seconds+' 秒';
    if (currentCall !== state.call_id) {
      sound.stop(); ringStartedFor = null;
      currentCall = state.call_id; mutedCall = null; ringPlan = Object.assign({},state.ring_preferences || preferences); clearPicture();
      try { if (sessionStorage.getItem('lynx-muted-call') === currentCall) mutedCall = currentCall; } catch (_) {}
      $('#mute').textContent = mutedCall ? '铃声已静音' : '本次静音';
      if (active) { document.body.classList.remove('dim'); $('#controls').hidden = true; message(''); }
    }
    $('#idle').hidden = active; $('#call').hidden = !active;
    $('#panelName').textContent = state.panel || '门口机';
    $('#callKind').textContent = state.direction === 'outgoing' ? '门口机预览' : '有访客 · 来访视频';
    $('#hangup').textContent = state.direction === 'outgoing' ? '结束预览' : '结束来访';
    if (!state.video_ready) { clearPicture(); $('#pictureHint').hidden = false; $('#pictureHint').textContent = active ? '等待新鲜视频画面' : ''; }
    else if (!imageURL) { $('#pictureHint').hidden = false; $('#pictureHint').textContent = '正在获取视频画面'; }
    const key = JSON.stringify(state.panels);
    if ($('#panels').dataset.panels !== key) {
      $('#panels').dataset.panels = key; $('#panels').replaceChildren();
      state.panels.forEach(panel => { const button = document.createElement('button');
        button.textContent = '查看 '+panel.name; button.addEventListener('click', () => control('preview',panel.id)); $('#panels').append(button); });
    }
    $('#recent').replaceChildren();
    state.events.forEach(event => { const item = document.createElement('li');
      item.textContent = new Date((event.time+(state.utc_offset || 0))*1000).toLocaleTimeString('zh-CN',{timeZone:'UTC',hour:'2-digit',minute:'2-digit',hour12:false})+'  '+(eventNames[event.kind] || '活动');
      $('#recent').append(item);
    });
    if (!state.events.length) { const item = document.createElement('li'); item.textContent = '暂无近期来访'; $('#recent').append(item); }
    const automatic = state.events.find(event => event.kind === 'open_auto' && event.call_id === state.call_id && event.id > lastAutoResult);
    if (automatic) { lastAutoResult = automatic.id; message('自动开门：门口机已确认。'); }
    if (pending) {
      const outcome = state.events.find(event => event.id > pending.after && event.call_id === pending.call &&
        (event.kind === 'call_ended' || event.request_id === pending.id) &&
        (pending.action === 'open' ? ['open_manual','open_denied','open_unknown','control_failed'].includes(event.kind) :
          ['call_ended','control_failed'].includes(event.kind)));
      if (outcome) { message(eventNames[outcome.kind]); pending = null; }
    }
    if (state.call === 'busy') message('另一个未授权门口机的会话正在进行，请稍候。');
    buttons(); updateClock(); ring();
  }
  async function setup(text) {
    stopped = true; ++generation; if (stream) stream.abort();
    clearTimeout(retryTimer); clearTimeout(renewTimer); offline('需要重新授权');
    $('#phone').hidden = true; $('#setup').hidden = false; message(text);
    $('#enrollForm').hidden = true;
    try {
      const data = await request('/v1/state');
      $('#enrollPanels').replaceChildren();
      data.panels.forEach(panel => { const label = document.createElement('label'), input = document.createElement('input');
        input.type = 'checkbox'; input.name = 'panel'; input.value = panel.id; input.checked = true;
        label.append(input, document.createTextNode(panel.name)); $('#enrollPanels').append(label); });
      $('#enrollForm').hidden = false;
    } catch (_) { $('#setupHint').textContent = '请先进入右上角“管理登录”，登录后再次打开话机模式。'; }
  }
  function reconnect(delay=0) {
    if (stopped || document.hidden) return;
    clearTimeout(retryTimer); clearTimeout(renewTimer);
    if (stream) stream.abort();
    const run = ++generation;
    retryTimer = setTimeout(() => connect(run), delay);
  }
  async function connect(run) {
    const abort = new AbortController(); stream = abort;
    const firstSnapshotTimeout = setTimeout(() => abort.abort(), 45000);
    let renewedSession = false;
    try {
      const renewed = await request('/v1/phone/session', {});
      if (run !== generation) return;
      renewedSession = true;
      $('#deviceName').textContent = renewed.device.name;
      const response = await fetch('/v1/phone/events', {signal:abort.signal, cache:'no-store',
        headers:cursor ? {'Last-Event-ID':cursor} : {}});
      if (run !== generation) return;
      if (!response.ok) { const error = Error('状态连接失败'); error.status = response.status; throw error; }
      if (!response.body || !response.body.getReader) throw Error('浏览器不支持状态流，请更新浏览器');
      renewTimer = setTimeout(() => reconnect(), 240000);
      const reader = response.body.getReader(), decoder = new TextDecoder(); let buffer = '';
      while (run === generation) {
        const chunk = await reader.read();
        if (run !== generation) return;
        if (chunk.done) throw Error('状态连接已断开');
        buffer += decoder.decode(chunk.value, {stream:true});
        if (buffer.length > 65536) throw Error('状态消息超出限制');
        let boundary;
        while ((boundary = buffer.indexOf('\n\n')) >= 0) {
          const block = buffer.slice(0,boundary); buffer = buffer.slice(boundary+2);
          if (block.includes('event: unauthorized')) { const error = Error('设备授权失效'); error.status = 401; throw error; }
          const line = block.split('\n').find(value => value.startsWith('data: '));
          if (line) { render(JSON.parse(line.slice(6))); clearTimeout(firstSnapshotTimeout); }
        }
      }
    } catch (error) {
      if (run !== generation) return;
      abort.abort(); clearTimeout(renewTimer);
      if (error.status === 401 && renewedSession && !authorizationRetry) {
        authorizationRetry = true; offline('正在恢复设备会话'); reconnect(1000); return;
      }
      if (error.status === 401 || error.status === 403) { await setup(error.message); return; }
      offline('连接中断，正在恢复');
      const delay = Math.min(30000, 1000*Math.pow(2, Math.min(attempt++,5)))*(0.8+Math.random()*0.2);
      reconnect(delay);
    } finally { clearTimeout(firstSnapshotTimeout); }
  }
  async function frame() {
    if (frameBusy || !online || !state || !state.video_ready || document.hidden) return;
    frameBusy = true; const call = state.call_id, run = generation;
    const abort = new AbortController(), timeout = setTimeout(() => abort.abort(), 5000);
    try {
      const response = await fetch('/v1/phone/frame.jpg', {cache:'no-store',signal:abort.signal});
      if (response.status === 401 || response.status === 403) {
        if (run === generation) {
          if (response.status === 401 && !authorizationRetry) { authorizationRetry = true; offline('正在恢复设备会话'); reconnect(); }
          else await setup('设备授权失效');
        }
        return;
      }
      if (!response.ok) throw Error('视频暂不可用');
      const blob = await response.blob();
      if (!online || run !== generation || state.call_id !== call) return;
      const next = URL.createObjectURL(blob), previous = imageURL;
      $('#picture').src = next; $('#picture').hidden = false; $('#pictureHint').hidden = true;
      imageURL = next; if (previous) URL.revokeObjectURL(previous);
    } catch (_) { if (run === generation) { clearPicture(); $('#pictureHint').hidden = false; $('#pictureHint').textContent = '视频暂停，正在等待新画面'; } }
    finally { clearTimeout(timeout); frameBusy = false; }
  }
  async function control(action, panel=null) {
    if (!online || !state || pending) return;
    const call = state.call_id;
    const bytes = new Uint8Array(16); crypto.getRandomValues(bytes);
    const id = Array.from(bytes, b => b.toString(16).padStart(2,'0')).join('');
    pending = {id, action, call, after:Math.max(0,...state.events.map(event => event.id)), time:performance.now()};
    buttons(); message('请求已提交，等待网关结果…');
    try {
      await request('/v1/phone/control', {action,panel,call_id:call,request_id:id});
      if (pending && pending.id === id && action === 'preview') { pending = null; message('预览请求已排队，等待画面。'); }
    } catch (error) {
      if (!pending || pending.id !== id) return;
      pending = null;
      if (error.status === 401) await setup(error.message);
      else message(error.status ? error.message : '操作结果未知；不会自动重试，请核对当前状态。');
    } finally { buttons(); }
  }
  function ringRemaining() {
    return ringPlan ? Math.max(0,ringPlan.ring_seconds-(state.call_age || 0)-(performance.now()-sampledAt)/1000) : 0;
  }
  function ring() {
    if (state && state.call_id) $('#mute').textContent = mutedCall === state.call_id ? '铃声已静音' : sound.enabled ? '本次静音' : '启用铃声';
    if (!sound.enabled) { if (sound.mode === 'call') sound.stop(); $('#soundStatus').textContent = '♪ 铃声未启用'; return; }
    const volume = Number($('#volume').value)/100;
    const eligible = online && state && !document.hidden && state.direction === 'incoming' && ['ringing','early_video'].includes(state.call) && mutedCall !== state.call_id;
    const remaining = eligible ? ringRemaining() : 0;
    $('#soundStatus').textContent = mutedCall && state && mutedCall === state.call_id ? '♪ 本次已静音' : !volume ? '♪ 铃声音量为零' : eligible && remaining <= 0 ? '♪ 本次响铃已结束' : '♪ 铃声已启用';
    if (!eligible || remaining <= 0 || !volume) { if (sound.mode === 'call') sound.stop(); return; }
    if (ringStartedFor === state.call_id) return;
    const call = state.call_id; ringStartedFor = call;
    sound.play(ringPlan,remaining,volume).catch(() => {
      if (!online || !state || state.call_id !== call || mutedCall === call || !Number($('#volume').value) || ringRemaining() <= 0) return;
      message('自定义音乐暂不可用，已改用清脆门铃。');
      sound.play({ringtone:'chime'},ringRemaining(),volume).catch(() => { message('铃声无法播放，请轻触启用并检查设备音量。'); });
    });
  }
  async function keepAwake() {
    if (!navigator.wakeLock || !window.isSecureContext) return;
    try { if (wakeLock && !wakeLock.released) return; wakeLock = await navigator.wakeLock.request('screen');
      $('#wakeHint').textContent = '已请求保持亮屏。切入后台或锁屏仍可能中断话机。';
      wakeLock.addEventListener('release', () => { $('#wakeHint').textContent = '保持亮屏已释放，请检查系统自动锁定设置。'; });
    } catch (_) { $('#wakeHint').textContent = '无法保持亮屏，请在系统设置中调整自动锁定。'; }
  }
  $('#enableSound').addEventListener('click', async () => {
    try {
      await sound.enable();
      if (state && state.direction === 'incoming' && ringRemaining() > 0 && mutedCall !== state.call_id) { ringStartedFor = null; ring(); }
      else await sound.play(state && state.phone_preferences || {ringtone:'chime'},3,Number($('#volume').value)/100,'preview');
      message('正在试听，请确认设备音量。',true); await keepAwake();
    } catch (_) { $('#soundStatus').textContent = '♪ 铃声被阻止'; message('浏览器未允许铃声或音乐不可用，请再次轻触启用并检查静音设置。'); }
  });
  $('#clockStyle').addEventListener('change',event => { clock.value.style = event.target.value; clock.save(); updateClock(); });
  $('#secondsMode').addEventListener('change',event => { clock.value.seconds = event.target.value; clock.save(); updateClock(); });
  $('#volume').addEventListener('input',event => { clock.value.volume = Number(event.target.value); clock.save(); sound.volume(clock.value.volume/100); if (clock.value.volume && sound.mode !== 'call') ringStartedFor = null; ring(); });
  $('#enrollForm').addEventListener('submit', async event => {
    event.preventDefault(); $('#enrollButton').disabled = true;
    try { await request('/v1/phone/enroll', {name:$('#deviceLabel').value,password:$('#adminPassword').value,
      panels:Array.from(document.querySelectorAll('[name=panel]:checked'),input => input.value)});
      $('#adminPassword').value = ''; stopped = false; message('请轻触“启用并试听铃声”。'); showControls(); reconnect();
    } catch (error) { message(error.message); }
    finally { $('#adminPassword').value = ''; $('#enrollButton').disabled = false; }
  });
  $('#wakeSurface').addEventListener('click', showControls);
  $('#hideControls').addEventListener('click', hideControls);
  $('#controls').addEventListener('pointerdown', showControls);
  $('#open').addEventListener('click', () => control('open'));
  $('#hangup').addEventListener('click', () => control('hangup'));
  $('#mute').addEventListener('click', async () => {
    if (!sound.enabled && state && mutedCall !== state.call_id) {
      try { await sound.enable(); ringStartedFor = null; ring(); if (ringRemaining() <= 0) message('本次响铃时段已结束，下一次来访可正常响铃。',true); }
      catch (_) { message('浏览器未允许铃声，请检查设备音量后重试。'); }
      return;
    }
    mutedCall = state && state.call_id; sound.stop(); try { sessionStorage.setItem('lynx-muted-call',mutedCall); } catch (_) {} $('#mute').textContent = '铃声已静音'; });
  $('#logout').addEventListener('click', async () => {
    try { await request('/v1/phone/session/logout', {}); await setup('此话机授权已撤销。'); }
    catch (error) { message('未能撤销设备，请恢复连接后重试：'+error.message); }
  });
  function resume() { if (!document.hidden && !stopped) { offline('正在恢复连接'); reconnect(); if (sound.enabled) keepAwake(); } }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { ++generation; if (stream) stream.abort(); clearTimeout(retryTimer); clearTimeout(renewTimer); offline('页面已暂停'); }
    else resume();
  });
  window.addEventListener('pageshow', resume); window.addEventListener('online', resume);
  window.addEventListener('offline', () => { ++generation; if (stream) stream.abort(); offline('网络已断开'); });
  window.addEventListener('pagehide', () => { ++generation; if (stream) stream.abort(); clearTimeout(retryTimer); clearTimeout(renewTimer); sound.stop(); clearPicture(); });
  setInterval(() => {
    updateClock(); ring();
    if (online && performance.now()-lastMessage > 45000) { offline('心跳已超时'); reconnect(); }
    if (pending && performance.now()-pending.time > 10000) { pending = null; message('操作结果尚未确认；不会自动重试。'); buttons(); }
  }, 1000);
  setInterval(frame, 1000);
  showControls(); reconnect();
})();
