const $=s=>document.querySelector(s);let logged=false,before=null,lastEvent=null,imageURL=null,reading=false,panelKey=null,loadedOlder=false;
let stateOnline=false,autoPending=false,autoPolicy=null,refreshing=null,activeVideoCall=null;
function logoutView(){clearAdminFrame();logged=false;stateOnline=false;autoPolicy=null;$('#workspace').hidden=true;$('#login').hidden=false;window.dispatchEvent(new Event('fermax-logout'));}
async function api(path,data){
  const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),8000);
  try{const r=await fetch(path,{method:data===undefined?'GET':'POST',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data),signal:abort.signal});const b=await r.json();if(!r.ok){if(r.status===401)logoutView();const e=Error(b.error||'请求失败');e.status=r.status;throw e}return b}
  finally{clearTimeout(timeout)}
}
const error=e=>{$('#error').textContent=e.message};
function renderStatistics(stats){
  const valid=stateOnline && stats && stats.available;
  $('#statsIncoming').textContent=valid?stats.incoming:'—';$('#statsOpenings').textContent=valid?stats.openings:'—';
  $('#statsDate').textContent=stats?stats.date:'';
  $('#statsStatus').textContent=!stateOnline?'连接中断，统计不可用':!valid?'统计暂不可用':'网关本地日期 · 开门含手动与自动协议确认，不代表物理门状态。';
}
function renderAuto(){
  const enabled=autoPolicy && autoPolicy.enabled;
  $('#autoSetup').hidden=!stateOnline||!!enabled;
  $('#disableAuto').hidden=!stateOnline||!enabled;
  $('#duration').disabled=$('#enableAuto').disabled=$('#disableAuto').disabled=!stateOnline||autoPending;
  $('.policy').dataset.active=String(!!enabled && stateOnline);
  $('#autoState').textContent=!stateOnline?'状态暂不可确认':enabled?(autoPolicy.minutes===0?'已启用 · 无时限':'已启用 · 限时'):'自动开门已停止';
  $('#autoDetail').textContent=!stateOnline?'连接恢复后将重新读取网关状态。':enabled?(autoPolicy.minutes===0?'收到来访时自动处理，直到你主动停止。':'截止 '+new Date(autoPolicy.expires_at*1000).toLocaleString('zh-CN')):'选择持续时间后启用。';
  $('#autoFeedback').textContent=autoPending?'正在提交，请稍候…':'';
}
$('#loginForm').addEventListener('submit',async e=>{e.preventDefault();try{await api('/v1/login',{password:$('#password').value});$('#password').value='';await update()}catch(e){error(e)}});
async function refreshState(){
  let s;
  try{s=await api('/v1/state');}
  catch(e){stateOnline=false;clearAdminFrame();renderAuto();renderStatistics(null);$('#network').textContent='网关连接中断';document.querySelectorAll('[data-action]').forEach(button=>button.disabled=true);$('#video').hidden=true;$('#videoHint').hidden=false;if(logged)error(e);return false}
  logged=true;stateOnline=true;renderStatistics(s.statistics);if(!s.clock.synchronized)$('#statsStatus').textContent+=' 网关时间未同步。';autoPolicy=s.auto;$('#workspace').hidden=false;$('#login').hidden=true;renderAuto();
  $('#identity').textContent=s.identity.building+' · '+s.identity.unit;renderPanels(s.panels);
  $('#clock').textContent=new Date(s.time*1000).toLocaleTimeString('zh-CN',{hour12:false});
  $('#clockSource').textContent=(s.clock.synchronized?'已对时 · ':'未同步 · ')+(s.clock.source==='dhcp'?'DHCP NTP':'公共 NTP');
  $('#network').textContent=s.network==='ready'?'门禁网络已连接':'等待门禁网络';
  $('#callState').textContent=({idle:'等待来访',ringing:'正在连接',early_video:'视频已接通',audio:'通话中',ending:'正在挂断'}[s.call]||s.call)+(s.panel?' · '+s.panel:'');$('#notice').textContent=s.notice;
  $('#open').disabled=!s.allow_open||!s.relays.length||!['early_video','audio'].includes(s.call);$('#answer').disabled=!s.audio_available||s.call!=='early_video';$('#hangup').disabled=!['ringing','early_video','audio'].includes(s.call);document.querySelectorAll('[data-action=preview]').forEach(b=>b.disabled=s.network!=='ready'||s.call!=='idle');
  if(!loadedOlder&&s.events[0]?.id!==lastEvent){lastEvent=s.events[0]?.id;logs(false).catch(error)}
  if(s.video_ready){activeVideoCall=s.call_id;frame().catch(error)}else{clearAdminFrame()}
  return true;
}
async function update(force=false){
  if(autoPending&&!force)return false;
  if(refreshing)return refreshing;
  refreshing=refreshState();try{return await refreshing}finally{refreshing=null}
}
async function changeAuto(minutes){
  if(autoPending||!stateOnline)return;
  autoPending=true;$('#error').textContent='';renderAuto();
  try{
    // Drain a pre-existing poll; polls cannot race this write and its confirmation.
    if(refreshing)await refreshing;
    if(!stateOnline)throw Error('连接中断，未提交设置。');
    await api('/v1/auto',{minutes});
    if(!await update(true))throw Error('设置结果暂不可确认，请等待连接恢复。');
  }catch(e){
    if(!e.status){stateOnline=false;}
    error(e);
  }finally{autoPending=false;renderAuto()}
}
function clearAdminFrame(){activeVideoCall=null;$('#video').hidden=true;$('#video').removeAttribute('src');$('#videoHint').hidden=false;if(imageURL)URL.revokeObjectURL(imageURL);imageURL=null;}
async function frame(){
  if(reading||!activeVideoCall)return;
  reading=true;const call=activeVideoCall,abort=new AbortController(),timer=setTimeout(()=>abort.abort(),5000);
  try{const r=await fetch('/v1/frame.jpg',{signal:abort.signal});if(r.ok){const blob=await r.blob();if(!logged||!stateOnline||call!==activeVideoCall)return;const next=URL.createObjectURL(blob);$('#video').src=next;$('#video').hidden=false;$('#videoHint').hidden=true;if(imageURL)URL.revokeObjectURL(imageURL);imageURL=next}}
  finally{clearTimeout(timer);reading=false}
}
async function control(button){button.disabled=true;try{await api('/v1/control',{action:button.dataset.action,panel:button.dataset.panel||null,request_id:crypto.randomUUID?crypto.randomUUID():Date.now()+'-'+Math.random()});await update()}catch(e){error(e)}finally{setTimeout(update,500)}}
document.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>control(b)));
function renderPanels(panels){const key=JSON.stringify(panels);if(key===panelKey)return;panelKey=key;$('#panelButtons').replaceChildren();for(const panel of panels){const b=document.createElement('button');b.textContent=panel.name;b.dataset.action='preview';b.dataset.panel=panel.id;b.addEventListener('click',()=>control(b));$('#panelButtons').append(b)}}
$('#enableAuto').addEventListener('click',()=>changeAuto(Number($('#duration').value)));
$('#disableAuto').addEventListener('click',()=>changeAuto(null));
$('#logout').addEventListener('click',()=>api('/v1/logout',{}).then(logoutView).catch(error));
window.addEventListener('offline',()=>{stateOnline=false;clearAdminFrame();renderAuto();renderStatistics(null)});
window.addEventListener('online',()=>{if(logged)update()});
document.addEventListener('visibilitychange',()=>{if(logged&&!document.hidden)update()});
async function logs(older){loadedOlder=older;const q=new URLSearchParams({limit:'50',kind:$('#kind').value});if(older&&before)q.set('before',before);const result=await api('/v1/logs?'+q);if(!older)$('#events').replaceChildren();for(const e of result.events){const tr=document.createElement('tr');for(const value of [new Date(e.time*1000).toLocaleString('zh-CN'),e.text]){const td=document.createElement('td');td.textContent=value;tr.append(td)}const td=document.createElement('td'),details=document.createElement('details'),summary=document.createElement('summary'),pre=document.createElement('pre');summary.textContent=e.kind;pre.textContent=JSON.stringify(e.detail,null,2);details.append(summary,pre);td.append(details);tr.append(td);$('#events').append(tr)}before=result.next_before;$('#older').disabled=result.events.length<50}
$('#older').addEventListener('click',()=>logs(true).catch(error));$('#refreshLogs').addEventListener('click',()=>logs(false).catch(error));$('#kind').addEventListener('change',()=>logs(false).catch(error));update();setInterval(()=>{if(logged)update()},1500);
