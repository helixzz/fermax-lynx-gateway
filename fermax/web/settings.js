const settingsPanel=document.querySelector('#settings');
const musicSection=document.createElement('section');
musicSection.id='phoneMusicSettings';
musicSection.innerHTML=`<div class="sectionHead"><div><span class="eyebrow">PHONE EXPERIENCE</span><h3>让门铃，也有家的声音。</h3></div><span class="badge">管理员设置</span></div>
<p class="muted">统一设置网关与所有话机的来访铃声。新设置用于下一次来访；不会改变自动开门策略。</p>
<form id="phoneMusicForm"><div class="settingsGrid"><label>铃声音乐<select id="ringtoneChoice"><option value="custom">自定义音乐</option></select></label><label>循环响铃时长<select id="ringDuration"><option value="15">15 秒</option><option value="30" selected>30 秒（默认）</option><option value="45">45 秒</option><option value="60">60 秒</option></select></label></div>
<div class="controls"><button id="previewRingtone" type="button">试听所选</button><button id="stopRingtone" type="button" class="quiet">停止试听</button><button class="primary">保存铃声设置</button></div><p id="savedMusic" class="muted"></p><div id="ringtoneLibrary" class="ringtoneLibrary" aria-label="预置铃声"></div></form>
<div class="music-upload"><label>上传喜欢的音乐<input id="ringtoneFile" type="file" accept="audio/*,.mp3,.wav,.m4a"></label><p class="muted">MP3、WAV 或 M4A；最长 60 秒、最大 10 MB。能否读取取决于管理浏览器。只保留最近上传的一首，请使用有权使用的音乐。</p><button id="uploadRingtone" type="button">上传并选择</button><p id="musicStatus" role="status" class="muted">尚未上传自定义音乐</p></div>`;
settingsPanel.querySelector('.settingsNav').after(musicSection);
const musicPlayer=new window.LynxSound();let musicSettings=null, previewTimer, previewGeneration=0;
const ringtoneNames=Object.fromEntries(window.LynxRingtones.map(track=>[track.id,track.name]));ringtoneNames.custom='自定义音乐';
const choice=document.querySelector('#ringtoneChoice'),library=document.querySelector('#ringtoneLibrary');
for(const group of [...new Set(window.LynxRingtones.map(track=>track.group))]){
  const options=document.createElement('optgroup');options.label=group;
  for(const track of window.LynxRingtones.filter(track=>track.group===group)){
    const option=document.createElement('option');option.value=track.id;option.textContent=track.name;options.append(option);
    const button=document.createElement('button');button.type='button';button.dataset.tone=track.id;button.setAttribute('aria-pressed','false');
    const name=document.createElement('strong'),detail=document.createElement('span');name.textContent=track.name;detail.textContent=group+' · 选择并试听';button.append(name,detail);
    button.addEventListener('click',()=>{choice.value=track.id;markMusic();previewMusic().catch(error)});library.append(button);
  }
  choice.insertBefore(options,choice.querySelector('[value="custom"]'));
}
function markMusic(){document.querySelectorAll('[data-tone]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.tone===choice.value)));}
function stopMusic(){previewGeneration++;clearTimeout(previewTimer);musicPlayer.stop();}
async function previewMusic(){stopMusic();const generation=previewGeneration;await musicPlayer.enable();if(generation!==previewGeneration)return;const value=selectedMusic(),track=window.LynxRingtones.find(track=>track.id===value.ringtone);const seconds=track?track.beats.reduce((sum,n)=>sum+n,0)*60/track.bpm+1.1:8;await musicPlayer.play(value,seconds,.5,'preview','/v1/ringtone');if(generation!==previewGeneration)return;document.querySelector('#musicStatus').textContent='正在试听 · '+ringtoneNames[value.ringtone];previewTimer=setTimeout(()=>{document.querySelector('#musicStatus').textContent='试听已结束。选择音乐后请保存设置。';},seconds*1000);}
choice.addEventListener('change',()=>{stopMusic();markMusic();});
function showMusic(value){musicSettings=value;document.querySelector('#ringtoneChoice').value=value.ringtone;document.querySelector('#ringDuration').value=value.ring_seconds;document.querySelector('#musicStatus').textContent=value.custom_available?'自定义音乐已就绪，可选择并保存。':'可选择 16 首预置铃声，或上传自己的音乐。';document.querySelector('#savedMusic').textContent='当前已保存：'+ringtoneNames[value.ringtone]+' · '+value.ring_seconds+' 秒';markMusic();}
async function refreshMusic(){showMusic(await api('/v1/phone-preferences'));}
function selectedMusic(){return Object.assign({},musicSettings,{ringtone:document.querySelector('#ringtoneChoice').value,ring_seconds:Number(document.querySelector('#ringDuration').value)});}
document.querySelector('#phoneMusicForm').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter || event.currentTarget.querySelector('button.primary');button.disabled=true;
  try{const value=selectedMusic();showMusic(await api('/v1/phone-preferences',{ringtone:value.ringtone,ring_seconds:value.ring_seconds}));document.querySelector('#musicStatus').textContent='已保存 · 下一次来访使用新铃声和时长。';}
  catch(e){error(e)}finally{button.disabled=false;stopMusic();}});
document.querySelector('#previewRingtone').addEventListener('click',()=>previewMusic().catch(error));
document.querySelector('#stopRingtone').addEventListener('click',()=>{stopMusic();document.querySelector('#musicStatus').textContent='试听已停止。';});
document.querySelector('#uploadRingtone').addEventListener('click',async event=>{const button=event.currentTarget;button.disabled=true;stopMusic();
  try{const body=await musicPlayer.importMusic(document.querySelector('#ringtoneFile').files[0]);const response=await fetch('/v1/ringtone',{method:'POST',headers:{'Content-Type':'audio/wav'},body});const result=await response.json();if(!response.ok)throw Error(result.error||'上传失败');showMusic(result);document.querySelector('#ringtoneChoice').value='custom';markMusic();document.querySelector('#musicStatus').textContent='上传完成 · 点击“保存铃声设置”使用这首音乐。';document.querySelector('#ringtoneFile').value='';}
  catch(e){error(e)}finally{button.disabled=false;}});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopMusic();});
window.addEventListener('pagehide',stopMusic);
window.addEventListener('fermax-logout',()=>{stopMusic();closeSettings();});
const deviceSection=document.createElement('section');deviceSection.id='phoneDevicesSettings';
deviceSection.innerHTML='<h3>已授权的话机设备</h3><p>设备只能查看近期来访及控制指定门口机。撤销后，话机连接随即失效。</p><button id="refreshDevices" type="button">刷新设备列表</button><ul id="deviceList"></ul><form id="revokeDeviceForm"><label>撤销设备<select id="revokeDeviceId" required></select></label><label>再次验证管理员密码<input id="revokePassword" type="password" autocomplete="current-password" required></label><button>撤销设备授权</button></form>';
settingsPanel.append(deviceSection);
async function refreshDevices(){
  const [result,snapshot]=await Promise.all([api('/v1/devices'),api('/v1/state')]);
  const panelNames=Object.fromEntries(snapshot.panels.map(panel=>[panel.id,panel.name]));
  const list=document.querySelector('#deviceList'),select=document.querySelector('#revokeDeviceId');
  list.replaceChildren();select.replaceChildren();
  for(const device of result.devices){const item=document.createElement('li'),option=document.createElement('option');
    item.textContent=device.name+' · '+device.panels.map(id=>panelNames[id]||id).join(' / ');list.append(item);
    option.value=device.id;option.textContent=device.name;select.append(option);
  }
  document.querySelector('#revokeDeviceForm').hidden=!result.devices.length;
  if(!result.devices.length)list.textContent='暂无授权设备';
}
document.querySelector('#refreshDevices').addEventListener('click',()=>refreshDevices().catch(error));
document.querySelector('#revokeDeviceForm').addEventListener('submit',async event=>{
  event.preventDefault();const password=document.querySelector('#revokePassword');
  try{await api('/v1/devices/revoke',{id:document.querySelector('#revokeDeviceId').value,password:password.value});await refreshDevices()}
  catch(e){error(e)}finally{password.value=''}
});
const integrationSection=document.createElement('section');integrationSection.id='integrationSettings';
integrationSection.innerHTML=`<h3>连接 Home Assistant</h3><p class="muted">直接连接网关，无需 MQTT。在 Home Assistant 安装 FERMAX LYNX Gateway 集成后，添加集成并输入网关地址和下方配对码。</p>
<form id="integrationPairForm"><div class="settingsGrid"><label>集成名称<input id="integrationName" value="Home Assistant" maxlength="60" required></label><label>再次验证管理员密码<input id="integrationPassword" type="password" autocomplete="current-password" required></label></div>
<fieldset><legend>允许访问的入口</legend><div id="integrationPanels" class="integrationOptions"></div></fieldset>
<fieldset><legend>授予权限</legend><p class="muted">默认只读：状态、统计和来访事件。以下权限可单独选用。</p><div class="integrationOptions">
<label><input type="checkbox" checked disabled>状态与统计（必选）</label><label><input type="checkbox" checked disabled>来访事件（必选）</label>
<label><input type="checkbox" name="integrationPermission" value="camera">查看当前画面</label><label><input type="checkbox" name="integrationPermission" value="preview">主动预览</label><label><input type="checkbox" name="integrationPermission" value="hangup">结束来访</label><label><input type="checkbox" name="integrationPermission" value="open" aria-describedby="integrationOpenWarning">允许开门</label></div>
<p id="integrationOpenWarning" class="integrationWarning">开门权限允许外部系统发送开门指令，包括它的自动化。请仅授予可信系统；默认关闭。</p></fieldset>
<button id="createIntegrationCode" class="primary" disabled>生成一次性配对码</button><p id="integrationPairStatus" class="muted" role="status"></p>
<div id="integrationCodeBox" class="integrationCodeBox" hidden><p>请现在复制到 Home Assistant；关闭此页面后不再显示。</p><code id="integrationCode"></code><p id="integrationCodeExpiry" class="muted"></p></div></form>
<div class="sectionHead"><h3>已授权的外部系统</h3><button id="refreshIntegrations" type="button" class="quiet">刷新列表</button></div><p class="muted">配对完成后刷新列表。撤销会立即终止该集成的访问；修改管理员密码也会撤销全部集成。</p><ul id="integrationList"></ul>
<form id="revokeIntegrationForm" hidden><div class="settingsGrid"><label>撤销集成<select id="revokeIntegrationId" required></select></label><label>再次验证管理员密码<input id="revokeIntegrationPassword" type="password" autocomplete="current-password" required></label></div><button>撤销集成授权</button></form>`;
settingsPanel.append(integrationSection);
const integrationTab=document.createElement('button');integrationTab.type='button';integrationTab.dataset.setting='integrationSettings';integrationTab.textContent='外部集成';integrationTab.setAttribute('aria-pressed','false');settingsPanel.querySelector('.settingsNav').append(integrationTab);
const integrationPermissionNames={state:'状态与统计',events:'来访事件',camera:'当前画面',preview:'主动预览',hangup:'结束来访',open:'开门'};
let integrationGeneration=0,integrationCodeTimer,integrationExpires=0,integrationLoading=false,integrationPairing=false;
function clearIntegrationCode(){
  integrationGeneration++;clearInterval(integrationCodeTimer);integrationExpires=0;
  document.querySelector('#integrationCode').textContent='';document.querySelector('#integrationCodeExpiry').textContent='';document.querySelector('#integrationCodeBox').hidden=true;
  document.querySelector('#integrationPassword').value='';document.querySelector('#revokeIntegrationPassword').value='';document.querySelector('#integrationPairStatus').textContent='';
}
function integrationActive(generation){return generation===integrationGeneration&&!settingsPanel.hidden&&!integrationSection.hidden;}
function updateIntegrationButton(){document.querySelector('#createIntegrationCode').disabled=integrationLoading||integrationPairing||!document.querySelector('#integrationPanels input:checked');}
async function refreshIntegrations(){
  if(integrationLoading)return;
  const generation=integrationGeneration;integrationLoading=true;updateIntegrationButton();
  const refresh=document.querySelector('#refreshIntegrations');refresh.disabled=true;
  try{
    const [result,snapshot]=await Promise.all([api('/v1/integrations'),api('/v1/state')]);
    if(!integrationActive(generation))return;
    const names=Object.fromEntries(snapshot.panels.map(panel=>[panel.id,panel.name]));
    const panels=document.querySelector('#integrationPanels');
    const selected=new Set(Array.from(panels.querySelectorAll('input:checked'),input=>input.value)),hadPanels=!!panels.children.length;
    panels.replaceChildren();
    for(const panel of snapshot.panels){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.value=panel.id;input.checked=hadPanels?selected.has(panel.id):true;input.addEventListener('change',updateIntegrationButton);label.append(input,document.createTextNode(panel.name));panels.append(label);}
    if(!snapshot.panels.length)panels.textContent='暂无可授权入口，请先配置门口机。';
    const list=document.querySelector('#integrationList'),select=document.querySelector('#revokeIntegrationId');list.replaceChildren();select.replaceChildren();
    for(const grant of result.integrations){const item=document.createElement('li'),name=document.createElement('strong'),detail=document.createElement('p'),option=document.createElement('option');
      name.textContent=grant.name;detail.className='muted';detail.textContent=grant.panels.map(id=>names[id]||id).join(' / ')+' · '+grant.permissions.map(key=>integrationPermissionNames[key]||key).join('、');item.append(name,detail);list.append(item);option.value=grant.id;option.textContent=grant.name;select.append(option);}
    if(!result.integrations.length)list.textContent='暂无已配对的外部系统';
    document.querySelector('#revokeIntegrationForm').hidden=!result.integrations.length;
  }catch(e){if(integrationActive(generation)){document.querySelector('#integrationPairStatus').textContent='无法读取集成或入口列表，请重试。';error(e);}}
  finally{integrationLoading=false;refresh.disabled=false;updateIntegrationButton();}
}
document.querySelector('#refreshIntegrations').addEventListener('click',refreshIntegrations);
document.querySelector('#integrationPairForm').addEventListener('submit',async event=>{
  event.preventDefault();if(integrationPairing||integrationLoading)return;
  const panels=Array.from(document.querySelectorAll('#integrationPanels input:checked'),input=>input.value);
  if(!panels.length){document.querySelector('#integrationPairStatus').textContent='请至少选择一个入口。';return;}
  const password=document.querySelector('#integrationPassword').value,name=document.querySelector('#integrationName').value.trim();
  if(!name){document.querySelector('#integrationPairStatus').textContent='请输入集成名称。';return;}
  const permissions=['state','events',...Array.from(document.querySelectorAll('[name="integrationPermission"]:checked'),input=>input.value)];
  clearIntegrationCode();const generation=integrationGeneration;integrationPairing=true;updateIntegrationButton();
  try{
    const result=await api('/v1/integrations/pairing',{password,name,panels,permissions});
    if(!integrationActive(generation))return;
    integrationExpires=Date.now()+Math.min(300,Number(result.expires_in)||0)*1000;
    document.querySelector('#integrationCode').textContent=result.code;document.querySelector('#integrationCodeBox').hidden=false;
    const tick=()=>{const seconds=Math.max(0,Math.ceil((integrationExpires-Date.now())/1000));if(!seconds){clearIntegrationCode();document.querySelector('#integrationPairStatus').textContent='配对码已过期，请重新生成。';return;}document.querySelector('#integrationCodeExpiry').textContent='剩余 '+seconds+' 秒 · 仅可使用一次，请勿分享给他人。';};
    tick();if(integrationExpires)integrationCodeTimer=setInterval(tick,1000);
  }catch(e){if(integrationActive(generation)){document.querySelector('#integrationPairStatus').textContent='未生成配对码，请检查密码后重试。';error(e);}}
  finally{integrationPairing=false;updateIntegrationButton();}
});
document.querySelector('#revokeIntegrationForm').addEventListener('submit',async event=>{
  event.preventDefault();const button=event.currentTarget.querySelector('button');if(button.disabled)return;
  const input=document.querySelector('#revokeIntegrationPassword'),password=input.value,id=document.querySelector('#revokeIntegrationId').value;input.value='';button.disabled=true;const generation=integrationGeneration;
  try{await api('/v1/integrations/revoke',{password,id});if(integrationActive(generation)){await refreshIntegrations();document.querySelector('#integrationPairStatus').textContent='已撤销该集成的访问权限。';}}
  catch(e){if(integrationActive(generation))error(e)}finally{button.disabled=false;}
});
window.addEventListener('pagehide',clearIntegrationCode);
window.addEventListener('fermax-logout',()=>{clearIntegrationCode();document.querySelector('#integrationPairForm').reset();document.querySelector('#integrationList').replaceChildren();document.querySelector('#integrationPanels').replaceChildren();document.querySelector('#revokeIntegrationId').replaceChildren();document.querySelector('#revokeIntegrationForm').hidden=true;updateIntegrationButton();});
const settingIds=['gatewayAudioSettings','phoneMusicSettings','phoneDevicesSettings','integrationSettings','configForm','passwordForm'];
function selectSettings(id){stopMusic();clearIntegrationCode();for(const pane of settingIds)document.getElementById(pane).hidden=pane!==id;document.querySelectorAll('[data-setting]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.setting===id)));if(id==='integrationSettings')refreshIntegrations();}
document.querySelectorAll('[data-setting]').forEach(button=>button.addEventListener('click',()=>selectSettings(button.dataset.setting)));
selectSettings('gatewayAudioSettings');
function closeSettings(){stopMusic();clearIntegrationCode();settingsPanel.hidden=true;document.querySelector('#overview').hidden=false;document.querySelector('.journal').hidden=false;document.querySelector('#showSettings').setAttribute('aria-expanded','false');document.querySelector('#showSettings').focus();}
document.querySelector('#backOverview').addEventListener('click',closeSettings);
document.querySelector('#showSettings').addEventListener('click',async()=>{
  if(!settingsPanel.hidden){closeSettings();return;}
  settingsPanel.hidden=false;document.querySelector('#overview').hidden=true;document.querySelector('.journal').hidden=true;document.querySelector('#showSettings').setAttribute('aria-expanded','true');stopMusic();
  try{
    const [, , result]=await Promise.all([refreshDevices(),refreshMusic(),api('/v1/config')]);
    for(const [key,value] of Object.entries(result.config)){
      const input=document.querySelector('[name="'+key+'"]');
      if(input)input.value=key==='panels'?JSON.stringify(value,null,2):value;
    }
    document.querySelector('#configStatus').textContent=result.restart_required?'已保存的配置等待服务重启生效。':'';
  }catch(e){error(e)}
});
document.querySelector('#configForm').addEventListener('submit',async event=>{
  event.preventDefault();
  const button=event.currentTarget.querySelector('button');button.disabled=true;
  try{
    const value=Object.fromEntries(new FormData(event.currentTarget));
    value.block=Number(value.block);value.extension=Number(value.extension);value.web_port=Number(value.web_port);
    value.panels=JSON.parse(value.panels);
    const result=await api('/v1/config',value);
    document.querySelector('#configStatus').textContent=result.restart_required?'配置已保存。请核对服务器网卡 IP，然后重启网关服务；当前连接暂不改变。':'配置已保存，当前已生效。';
  }catch(e){error(e)}finally{button.disabled=false}
});
document.querySelector('#passwordForm').addEventListener('submit',async event=>{
  event.preventDefault();
  const form=event.currentTarget, button=form.querySelector('button');button.disabled=true;
  try{
    const value=Object.fromEntries(new FormData(form));
    if(value.new_password!==value.confirm_password)throw Error('两次新密码不一致');
    await api('/v1/password',{current_password:value.current_password,new_password:value.new_password});
    form.reset();logoutView();
    error(Error('密码已修改，请使用新密码登录。其他网页会话也已退出。'));
  }catch(e){error(e)}finally{button.disabled=false}
});
