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
const settingIds=['gatewayAudioSettings','phoneMusicSettings','phoneDevicesSettings','configForm','passwordForm'];
function selectSettings(id){stopMusic();for(const pane of settingIds)document.getElementById(pane).hidden=pane!==id;document.querySelectorAll('[data-setting]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.setting===id)));}
document.querySelectorAll('[data-setting]').forEach(button=>button.addEventListener('click',()=>selectSettings(button.dataset.setting)));
selectSettings('gatewayAudioSettings');
function closeSettings(){stopMusic();settingsPanel.hidden=true;document.querySelector('#overview').hidden=false;document.querySelector('.journal').hidden=false;document.querySelector('#showSettings').setAttribute('aria-expanded','false');document.querySelector('#showSettings').focus();}
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
