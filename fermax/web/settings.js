const settingsPanel=document.querySelector('#settings');
const phoneLink=document.createElement('a');phoneLink.href='/phone';phoneLink.textContent='平板话机模式 ↗';phoneLink.className='button';
document.querySelector('#showSettings').before(phoneLink);
const deviceSection=document.createElement('section');
deviceSection.innerHTML='<hr><h3>已授权的话机设备</h3><p>设备只能查看近期来访及控制指定门口机。撤销后，话机连接随即失效。</p><button id="refreshDevices" type="button">刷新设备列表</button><ul id="deviceList"></ul><form id="revokeDeviceForm"><label>撤销设备<select id="revokeDeviceId" required></select></label><label>再次验证管理员密码<input id="revokePassword" type="password" autocomplete="current-password" required></label><button>撤销设备授权</button></form>';
settingsPanel.append(deviceSection);
async function refreshDevices(){
  const result=await api('/v1/devices');
  const list=document.querySelector('#deviceList'),select=document.querySelector('#revokeDeviceId');
  list.replaceChildren();select.replaceChildren();
  for(const device of result.devices){const item=document.createElement('li'),option=document.createElement('option');
    item.textContent=device.name+' · '+device.panels.join(' / ');list.append(item);
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
document.querySelector('#showSettings').addEventListener('click',async()=>{
  settingsPanel.hidden=!settingsPanel.hidden;
  if(!settingsPanel.hidden) try {
    await refreshDevices();
    const result=await api('/v1/config');
    for(const [key,value] of Object.entries(result.config)){
      const input=document.querySelector('[name="'+key+'"]');
      if(input)input.value=key==='panels'?JSON.stringify(value,null,2):value;
    }
    document.querySelector('#configStatus').textContent=result.restart_required?'已保存的配置等待服务重启生效。':'';
  } catch(e){error(e)}
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
    form.reset();settingsPanel.hidden=true;logged=false;
    document.querySelector('#workspace').hidden=true;document.querySelector('#login').hidden=false;
    error(Error('密码已修改，请使用新密码登录。其他网页会话也已退出。'));
  }catch(e){error(e)}finally{button.disabled=false}
});
