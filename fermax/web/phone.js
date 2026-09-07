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
  let soundFailed = false;
  const ringNames = Object.assign({custom:'自定义音乐'},Object.fromEntries(window.LynxRingtones.map(track=>[track.id,track.name])));
  const eventNames = {incoming:'收到来访', outgoing:'查看门口机', call_ended:'来访结束',
    open_manual:'门口机确认开门', open_auto:'自动开门已确认', open_unknown:'开门结果未知',
    open_denied:'开门被拒绝', control_failed:'操作未完成'};

  const icons = {
    bell:'M6 8a6 6 0 0 1 12 0v5l3 4H3l3-4V8m4 12h4',
    door:'M4 21V3h12v18M8 21h12V6l-8-3v18m3-9h.01',
    link:'M9 15l6-6M8 17l-1 1a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 0 1-1a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0',
    network:'M3 8a15 15 0 0 1 18 0M6 12a10 10 0 0 1 12 0m-9 4a5 5 0 0 1 6 0m-3 4h.01',
    auto:'M4 10a8 8 0 0 1 14-4l2 2m0-5v5h-5M20 14a8 8 0 0 1-14 4l-2-2m0 5v-5h5',
    down:'m5 9 7 7 7-7', camera:'M3 5h12v14H3zm12 5 6-3v10l-6-3',
    end:'M5 5l14 14M19 5 5 19', settings:'M4 7h16M4 17h16M8 4v6m8 4v6'
  };
  function icon(node, name, label, iconOnly=false, inactive=false) {
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.classList.add('ui-icon');
    const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',icons[name]);svg.append(path);
    if(inactive){const slash=document.createElementNS(svg.namespaceURI,'path');slash.setAttribute('d','M3 3 21 21');svg.append(slash);}
    const text=document.createElement('span');text.textContent=label;if(iconOnly)text.className='sr-only';
    node.replaceChildren(svg,text);node.setAttribute('aria-label',label);node.title=label;
  }
  function status(id,name,label,inactive=false){const node=$(id);icon(node,name,label,false,inactive);node.dataset.inactive=String(inactive);}
  function statistics() {
    const stats=state && state.statistics;
    const valid=online && stats && stats.available;
    for(const [id,name,key,label] of [['#todayIncoming','bell','incoming','今日来电'],['#todayOpenings','door','openings','今日已确认开门']]){
      const number=valid?String(stats[key]):'—';
      const detail=!online?'连接中断，统计不可用':!valid?'统计暂不可用':stats.date+' · '+label+' '+number+' 次'+(!state.clock_synchronized?' · 网关时间未同步':'')+(key==='openings'?' · 协议确认，非物理门状态':'');
      icon($(id),name,number);$(id).setAttribute('aria-label',detail);$(id).title=detail;
    }
  }
  icon($('#hideControls'),'down','收起操作面板',true);
  icon($('#open'),'door','开门');
  icon($('#showControls'),'settings','显示话机操作面板',true);

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
    status('#gatewayStatus','link',text,true);
    status('#networkStatus','network','连接中断，门禁状态待同步',true);
    status('#autoStatus','auto','连接中断，自动开门状态待同步',true); statistics();
    attention(); clearPicture(); buttons();
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
  function attention() {
    const auto = online && state && state.auto.enabled;
    $('#autoIndicator').hidden = !auto;
    if (auto) icon($('#autoIndicator'),'auto','自动开门已启用 · '+(state.auto.minutes === 0 ? '无时限' : '限时')+' · 查看状态',true);
    const issue = soundFailed || !sound.enabled || !Number($('#volume').value);
    $('#soundIndicator').hidden = !issue;
    if (issue) icon($('#soundIndicator'),'bell',soundFailed?'铃声播放受阻，打开声音设置':!Number($('#volume').value)?'铃声音量为零，打开声音设置':'铃声未启用，打开声音设置',true,true);
    const notice = !online ? '网关连接中断 · 正在恢复' : state && state.network !== 'ready' ? '门禁网络未就绪' : '';
    $('#connectionNotice').textContent = notice; $('#connectionNotice').hidden = !notice;
  }
  function armControlsTimer() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      if ($('#controls').contains(document.activeElement)) { armControlsTimer(); return; }
      if (state && state.call === 'idle') hideControls(false);
    },20000);
  }
  function showControls() {
    $('#controls').hidden = false; $('#controlsBackdrop').hidden=false; document.body.classList.remove('dim');
    $('#showControls').setAttribute('aria-expanded','true'); armControlsTimer();
  }
  function openControls(focus='#hideControls') { showControls(); $(focus).focus(); }
  function hideControls(restore=true) {
    $('#controls').hidden = true; $('#controlsBackdrop').hidden=true; document.body.classList.add('dim');
    $('#showControls').setAttribute('aria-expanded','false'); clearTimeout(hideTimer);
    if (restore && !$('#idle').hidden) $('#showControls').focus();
  }
  function clockDate() { return new Date(wall+(state.utc_offset || 0)*1000+performance.now()-sampledAt); }
  function smoothClock(timestamp) {
    if (document.hidden || !state || state.call_id || clock.value.style !== 'analog' || clock.value.seconds !== 'sweep' || matchMedia('(prefers-reduced-motion: reduce)').matches) { sweepFrame = null; return; }
    if (timestamp-lastSweep >= 80) { clock.update(clockDate()); lastSweep = timestamp; }
    sweepFrame = requestAnimationFrame(smoothClock);
  }
  function updateClock() {
    if (!wall) return;
    const face=$('#clockFace'), width=face.clientWidth;
    if(width && face.style.getPropertyValue('--face-width')!==width+'px') face.style.setProperty('--face-width',width+'px');
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
    $('#setup').hidden = true; $('#phone').hidden = false; document.body.classList.add('phone-ready');
    document.body.classList.remove('offline');
    status('#gatewayStatus','link','网关已连接'); statistics();
    status('#networkStatus','network',state.network === 'ready' ? '● 门禁已连接' : '○ 门禁未就绪',!state || state.network !== 'ready');
    status('#autoStatus','auto',state.auto.enabled ? '◉ 自动开门 · '+(state.auto.minutes === 0 ? '无时限' : '已启用') : '○ 自动开门已关闭',!state.auto.enabled);
    const active = !!state.call_id;
    const focusOutOfCall=!active && document.body.classList.contains('in-call') && $('#call').contains(document.activeElement);
    const focusIntoCall=active && !document.body.classList.contains('in-call') && ($('#idle').contains(document.activeElement) || $('#controls').contains(document.activeElement));
    document.body.classList.toggle('in-call',active);
    const preferences = state.phone_preferences || {ringtone:'chime',ring_seconds:30};
    $('#ringSetting').textContent = (ringNames[preferences.ringtone] || '清脆门铃')+' · 最长响铃 '+preferences.ring_seconds+' 秒';
    if (currentCall !== state.call_id) {
      sound.stop(); ringStartedFor = null;
      currentCall = state.call_id; mutedCall = null; ringPlan = Object.assign({},state.ring_preferences || preferences); clearPicture();
      try { if (sessionStorage.getItem('lynx-muted-call') === currentCall) mutedCall = currentCall; } catch (_) {}
      icon($('#mute'),'bell',mutedCall ? '铃声已静音' : '本次静音',true,!!mutedCall);
      if (active) { hideControls(false); document.body.classList.remove('dim'); message(''); }
    }
    $('#idle').hidden = active; $('#call').hidden = !active;
    if(focusIntoCall) $('#call').focus();
    if(focusOutOfCall) $('#showControls').focus();
    if(!active && !$('#controls').hidden && !$('#controls').contains(document.activeElement)) $('#hideControls').focus();
    $('#panelName').textContent = state.panel || '门口机';
    $('#callKind').textContent = state.direction === 'outgoing' ? '门口机预览' : '有访客 · 来访视频';
    icon($('#hangup'),'end',state.direction === 'outgoing' ? '结束预览' : '结束来访');
    if (!state.video_ready) { clearPicture(); $('#pictureHint').hidden = false; $('#pictureHint').textContent = active ? '等待新鲜视频画面' : ''; }
    else if (!imageURL) { $('#pictureHint').hidden = false; $('#pictureHint').textContent = '正在获取视频画面'; }
    const key = JSON.stringify(state.panels);
    if ($('#panels').dataset.panels !== key) {
      $('#panels').dataset.panels = key; $('#panels').replaceChildren();
      state.panels.forEach(panel => { const button = document.createElement('button');
        icon(button,'camera',panel.name);button.setAttribute('aria-label','查看 '+panel.name);button.title='查看 '+panel.name; button.addEventListener('click', () => control('preview',panel.id)); $('#panels').append(button); });
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
    hideControls(false); $('#phone').hidden = true; $('#setup').hidden = false; document.body.classList.remove('phone-ready'); message(text);
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
    attention();
    if (state && state.call_id) icon($('#mute'),'bell',mutedCall === state.call_id ? '铃声已静音' : sound.enabled ? '本次静音' : '启用铃声',true,!!mutedCall);
    if (!sound.enabled) { if (sound.mode === 'call') sound.stop(); status('#soundStatus','bell',soundFailed?'♪ 铃声播放受阻':'♪ 铃声未启用',soundFailed || !sound.enabled || !!mutedCall || !Number($('#volume').value)); return; }
    const volume = Number($('#volume').value)/100;
    const eligible = online && state && !document.hidden && state.direction === 'incoming' && ['ringing','early_video'].includes(state.call) && mutedCall !== state.call_id;
    const remaining = eligible ? ringRemaining() : 0;
    status('#soundStatus','bell',soundFailed ? '♪ 铃声播放受阻' : mutedCall && state && mutedCall === state.call_id ? '♪ 本次已静音' : !volume ? '♪ 铃声音量为零' : eligible && remaining <= 0 ? '♪ 本次响铃已结束' : '♪ 铃声已启用',soundFailed || !sound.enabled || !!mutedCall || !Number($('#volume').value));
    if (!eligible || remaining <= 0 || !volume) { if (sound.mode === 'call') sound.stop(); return; }
    if (ringStartedFor === state.call_id) return;
    const call = state.call_id; ringStartedFor = call;
    sound.play(ringPlan,remaining,volume).catch(() => {
      if (!online || !state || state.call_id !== call || mutedCall === call || !Number($('#volume').value) || ringRemaining() <= 0) return;
      message('自定义音乐暂不可用，已改用清脆门铃。');
      sound.play({ringtone:'chime'},ringRemaining(),volume).catch(() => { if (!online || !state || state.call_id !== call || mutedCall === call || ringRemaining() <= 0) return; soundFailed=true; attention(); message('铃声无法播放，请轻触启用并检查设备音量。'); });
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
      await sound.enable(); soundFailed=false; attention();
      if (state && state.direction === 'incoming' && ringRemaining() > 0 && mutedCall !== state.call_id) { ringStartedFor = null; ring(); }
      else await sound.play(state && state.phone_preferences || {ringtone:'chime'},3,Number($('#volume').value)/100,'preview');
      message('正在试听，请确认设备音量。',true); await keepAwake();
    } catch (_) { soundFailed=true; attention(); status('#soundStatus','bell','♪ 铃声被阻止',soundFailed || !sound.enabled || !!mutedCall || !Number($('#volume').value)); message('浏览器未允许铃声或音乐不可用，请再次轻触启用并检查静音设置。'); }
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
  $('#wakeSurface').addEventListener('click', () => openControls());
  $('#showControls').addEventListener('click', () => openControls());
  $('#autoIndicator').addEventListener('click', () => openControls());
  $('#soundIndicator').addEventListener('click', () => openControls('#enableSound'));
  $('#hideControls').addEventListener('click', () => hideControls());
  $('#controls').addEventListener('pointerdown', armControlsTimer);
  $('#controlsBackdrop').addEventListener('click', () => hideControls());
  $('#controls').addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); hideControls(); return; }
    armControlsTimer();
    if(event.key === 'Tab'){
      const items=Array.from($('#controls').querySelectorAll('button,a,input,select,summary,[tabindex="0"]')).filter(node=>!node.disabled && node.getClientRects().length);
      if(event.shiftKey && document.activeElement===items[0]){event.preventDefault();items[items.length-1].focus();}
      else if(!event.shiftKey && document.activeElement===items[items.length-1]){event.preventDefault();items[0].focus();}
    }
  });
  $('#open').addEventListener('click', () => control('open'));
  $('#hangup').addEventListener('click', () => control('hangup'));
  $('#mute').addEventListener('click', async () => {
    if (!sound.enabled && state && mutedCall !== state.call_id) {
      try { await sound.enable(); soundFailed=false; ringStartedFor = null; ring(); if (ringRemaining() <= 0) message('本次响铃时段已结束，下一次来访可正常响铃。',true); }
      catch (_) { soundFailed=true; attention(); message('浏览器未允许铃声，请检查设备音量后重试。'); }
      return;
    }
    mutedCall = state && state.call_id; sound.stop(); try { sessionStorage.setItem('lynx-muted-call',mutedCall); } catch (_) {} icon($('#mute'),'bell','铃声已静音',true,!!mutedCall); });
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
  if(window.ResizeObserver) new ResizeObserver(() => requestAnimationFrame(updateClock)).observe($('#clockFace'));
  window.addEventListener('resize',updateClock);
  setInterval(frame, 1000);
  hideControls(false); reconnect();
})();
