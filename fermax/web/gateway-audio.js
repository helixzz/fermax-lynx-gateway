/* Administrator-only gateway sound controls. Enumeration never plays audio. */
(() => {
  const pane=document.querySelector('#gatewayAudioSettings');
  const enabled=document.querySelector('#gatewayRingEnabled'),volume=document.querySelector('#gatewayRingVolume'),output=document.querySelector('#gatewayOutput');
  const feedback=document.querySelector('#gatewayAudioFeedback');
  let loaded=false,dirty=false,busy=false,polling=false,generation=0;
  const types={usb:'USB',analog:'3.5mm / 模拟',hdmi:'HDMI',other:'其他输出'};
  function show(result,force=false){
    if(force||!dirty){enabled.value=String(result.settings.enabled);volume.value=result.settings.volume;document.querySelector('#gatewayVolumeLabel').textContent=volume.value+'%';}
    const selection=force||!dirty?result.settings.output:output.value;
    output.replaceChildren(new Option('自动 · USB → 3.5mm → HDMI','auto'));
    for(const device of result.devices)output.add(new Option(types[device.kind]+' · '+device.name,device.id));
    if(selection!=='auto'&&!result.devices.some(d=>d.id===selection))output.add(new Option('首选设备未连接 · 保留偏好并自动降级',selection));
    output.value=selection;
    const list=document.querySelector('#gatewayAudioDevices');list.replaceChildren();
    for(const device of result.devices){const li=document.createElement('li'),name=document.createElement('strong'),detail=document.createElement('span');name.textContent=device.name;detail.textContent=types[device.kind]+' · '+device.status;li.append(name,detail);list.append(li);}
    if(!result.devices.length)list.textContent='未检测到播放设备。连接设备后列表会自动更新。';
    document.querySelector('#gatewayActualOutput').textContent=result.actual?result.actual.name:'当前未播放';
    document.querySelector('#gatewayAudioStatus').textContent=result.status;
    document.querySelector('#stopGatewayAudioTest').disabled=!result.testing;
    loaded=true;
  }
  async function refresh(){
    if(polling||busy||!logged||pane.hidden||settingsPanel.hidden||document.hidden)return;
    polling=true;const current=generation;
    try{const result=await api('/v1/gateway-audio');if(current===generation&&logged)show(result)}
    catch(e){if(current===generation){document.querySelector('#gatewayAudioStatus').textContent='连接中断，设置状态暂不可确认';feedback.textContent=e.message;loaded=false;}}
    finally{polling=false;}
  }
  for(const input of [enabled,volume,output])input.addEventListener('input',()=>{dirty=true;document.querySelector('#gatewayVolumeLabel').textContent=volume.value+'%';feedback.textContent='尚未保存。测试声音使用已保存的设置。';});
  async function action(path,data){
    if(busy||!loaded)return;busy=true;const current=++generation;
    const buttons=[...pane.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
    try{const result=await api(path,data);if(logged&&current===generation){if(path==='/v1/gateway-audio'){dirty=false;show(result,true);feedback.textContent='已保存。关闭立即停音；音量与输出用于下一次来访。';}else{show(result);feedback.textContent=data.stop?'已停止测试':'正在网关播放测试声音，请确认实际扬声器。';}}}
    catch(e){if(logged&&current===generation)feedback.textContent=e.message;}
    finally{busy=false;buttons.forEach(b=>b.disabled=false);refresh();}
  }
  document.querySelector('#gatewayAudioForm').addEventListener('submit',e=>{e.preventDefault();action('/v1/gateway-audio',{enabled:enabled.value==='true',volume:Number(volume.value),output:output.value});});
  document.querySelector('#testGatewayAudio').addEventListener('click',()=>action('/v1/gateway-audio/test',{stop:false}));
  document.querySelector('#stopGatewayAudioTest').addEventListener('click',()=>action('/v1/gateway-audio/test',{stop:true}));
  window.addEventListener('fermax-logout',()=>{generation++;loaded=false;dirty=false;});
  new MutationObserver(refresh).observe(settingsPanel,{attributes:true,subtree:true,attributeFilter:['hidden']});
  setInterval(refresh,1500);
})();
