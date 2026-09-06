const settingsPanel=document.querySelector('#settings');
document.querySelector('#showSettings').addEventListener('click',async()=>{
  settingsPanel.hidden=!settingsPanel.hidden;
  if(!settingsPanel.hidden) try {
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
    value.extension=Number(value.extension);value.web_port=Number(value.web_port);
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
