/* Real UI, synthetic loopback service only. Also generates the manual demo gallery. */
const {spawn,spawnSync}=require('node:child_process');
const {createInterface}=require('node:readline');
const {once}=require('node:events');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const browsers=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
  const fixture=spawn(process.env.PYTHON || 'python3',['-m','tests.phone_fixture','--demo'],{stdio:['pipe','pipe','inherit'],env:{...process.env,TZ:'UTC'}});
  const lines=createInterface({input:fixture.stdout});let browser;
  const directory=process.env.DEMO_DIR,captured=[];
  const hash=data=>require('node:crypto').createHash('sha256').update(data).digest('hex');
  if(directory)fs.mkdirSync(directory,{recursive:true});
  try{
    const {port}=JSON.parse((await once(lines,'line'))[0]),origin=`http://127.0.0.1:${port}`;
    async function scenario(command){
      let exited;const dead=new Promise((_,reject)=>{exited=()=>reject(Error('Synthetic fixture exited'));fixture.once('exit',exited)});
      try{const reply=Promise.race([once(lines,'line'),dead]);fixture.stdin.write(JSON.stringify({command})+'\n');return JSON.parse((await reply)[0]);}
      finally{fixture.removeListener('exit',exited);}
    }
    const engine=process.env.BROWSER_ENGINE || 'chromium';
    browser=await browsers[engine].launch({headless:true,executablePath:process.env.BROWSER_EXECUTABLE || undefined});
    const context=await browser.newContext({viewport:{width:1024,height:768},hasTouch:true,timezoneId:'UTC',reducedMotion:'reduce'});
    const errors=[];context.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));
    // Observe actual Web Audio scheduling without changing playback semantics.
    await context.addInitScript(()=>{
      window.__soundEvents=[];
      const Context=window.AudioContext || window.webkitAudioContext;
      if(!Context)return;
      const original=Context.prototype.createBufferSource;
      Context.prototype.createBufferSource=function(){const node=original.call(this),ctx=this,start=node.start.bind(node),stop=node.stop.bind(node);
        node.start=(...args)=>{window.__soundEvents.push({kind:'start',loop:node.loop,duration:node.buffer && node.buffer.duration});return start(...args)};
        node.stop=(when)=>{window.__soundEvents.push({kind:'stop',remaining:when===undefined?0:when-ctx.currentTime});return stop(when)};return node;};
    });
    const admin=await context.newPage();
    async function shot(page,name,locator){
      if(!directory)return;
      await page.evaluate(()=>document.fonts.ready);
      const png=locator ? await page.locator(locator).screenshot() : await page.screenshot({fullPage:false});
      const result=spawnSync(process.env.PYTHON || 'python3',['-c',"from PIL import Image;import io,sys;Image.open(io.BytesIO(sys.stdin.buffer.read())).save(sys.argv[1], 'WEBP', quality=88)",path.join(directory,name+'.webp')],{input:png});
      if(result.status!==0)throw Error(result.stderr.toString());
      captured.push({file:name+'.webp',sha256:hash(fs.readFileSync(path.join(directory,name+'.webp')))});
    }
    async function login(page){await page.goto(origin);await page.locator('#password').fill('synthetic-phone-password');await page.locator('#loginForm button').click();await page.locator('#workspace').waitFor({state:'visible'});}
    await admin.goto(origin);await admin.locator('#login').waitFor({state:'visible'});await shot(admin,'admin-login');
    await login(admin);await shot(admin,'admin-dashboard');
    async function noOverlap(){
      assert.equal(await admin.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
      const boxes=await admin.locator('.navActions > *').evaluateAll(nodes=>nodes.map(node=>{const r=node.getBoundingClientRect();return {left:r.left,top:r.top,right:r.right,bottom:r.bottom}}));
      for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){const a=boxes[i],b=boxes[j];assert.equal(a.left<b.right&&a.right>b.left&&a.top<b.bottom&&a.bottom>b.top,false);}
    }
    for(const [width,height] of [[1024,768],[768,1024],[390,844],[844,390]]){await admin.setViewportSize({width,height});await noOverlap();}
    await admin.setViewportSize({width:1024,height:768});await admin.evaluate(()=>document.body.style.zoom='2');await noOverlap();await shot(admin,'admin-zoom');await admin.evaluate(()=>document.body.style.zoom='');
    assert.equal(await admin.locator('#autoSetup').isVisible(),true);assert.equal(await admin.locator('#disableAuto').isVisible(),false);
    assert.equal(await admin.locator('#statsIncoming').textContent(),'0');
    await scenario('stats_seed');await admin.waitForFunction(()=>document.querySelector('#statsIncoming').textContent==='7');
    assert.equal(await admin.locator('#statsOpenings').textContent(),'4');await shot(admin,'admin-statistics','.adminStats');
    await admin.locator('#duration').selectOption('15');await admin.locator('#enableAuto').click();await admin.waitForFunction(()=>document.querySelector('#autoState').textContent.includes('限时'));
    assert.equal(await admin.locator('#autoSetup').isVisible(),false);await shot(admin,'admin-auto-timed');
    await scenario('auto_expire');await admin.locator('#autoSetup').waitFor({state:'visible'});
    await scenario('auto');await admin.waitForFunction(()=>document.querySelector('#autoState').textContent.includes('无时限'));await shot(admin,'admin-auto-unlimited');
    // HTTP failure must retain the confirmed enabled state and must not issue a retry.
    let posts=0;await admin.route('**/v1/auto',async route=>{posts++;await route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Synthetic write failure'})})});
    await admin.locator('#disableAuto').click();await admin.waitForFunction(()=>document.querySelector('#error').textContent.includes('Synthetic'));
    assert.equal(await admin.locator('#autoSetup').isVisible(),false);assert.equal(await admin.locator('#disableAuto').isEnabled(),true);assert.equal(posts,1);await admin.unroute('**/v1/auto');
    let release;const gate=new Promise(resolve=>release=resolve);let waiting=false;await admin.route('**/v1/auto',async route=>{waiting=true;await gate;await route.continue()});
    await admin.locator('#disableAuto').click();await admin.waitForFunction(()=>document.querySelector('#autoFeedback').textContent.includes('正在提交'));assert.equal(waiting,true);assert.equal(await admin.locator('#disableAuto').isDisabled(),true);
    release();await admin.locator('#autoSetup').waitFor({state:'visible'});await admin.unroute('**/v1/auto');
    await context.setOffline(true);await admin.waitForFunction(()=>document.querySelector('#autoState').textContent.includes('不可确认'));assert.equal(await admin.locator('#enableAuto').isVisible(),false);await shot(admin,'admin-offline');
    await context.setOffline(false);await admin.locator('#autoSetup').waitFor({state:'visible'});await admin.evaluate(()=>document.querySelector('#error').textContent='');
    // A late frame cannot repaint a visit after the state has ended it.
    await scenario('incoming');await admin.locator('#video').waitFor({state:'visible'});
    let frameRelease,frameReady;const frameGate=new Promise(resolve=>frameRelease=resolve),frameCaptured=new Promise(resolve=>frameReady=resolve);
    await admin.route('**/v1/frame.jpg',async route=>{const response=await route.fetch();frameReady();await frameGate;await route.fulfill({response});});
    await frameCaptured;await scenario('end');await admin.locator('#video').waitFor({state:'hidden'});
    const lateFrame=admin.waitForResponse('**/v1/frame.jpg');frameRelease();await lateFrame;await admin.waitForTimeout(80);assert.equal(await admin.locator('#video').isVisible(),false);await admin.unroute('**/v1/frame.jpg');
    await admin.locator('#showSettings').click();
    await admin.waitForFunction(()=>document.querySelector('#gatewayAudioDevices li'));
    for(const [width,height] of [[1024,768],[768,1024],[390,844],[844,390]]){
      await admin.setViewportSize({width,height});await noOverlap();
      await admin.evaluate(()=>document.body.style.zoom='2');await noOverlap();
      await admin.evaluate(()=>document.body.style.zoom='');
    }
    await admin.setViewportSize({width:1024,height:768});
    await shot(admin,'admin-gateway-sound','#gatewayAudioSettings');
    assert.equal(await admin.locator('#gatewayRingEnabled').inputValue(),'true');
    assert.equal(await admin.locator('#gatewayOutput option').count(),4);
    await admin.locator('#gatewayOutput').selectOption('a'.repeat(64));
    await admin.locator('#saveGatewayAudio').click();await admin.waitForFunction(()=>document.querySelector('#gatewayAudioFeedback').textContent.includes('已保存'));
    await admin.locator('#testGatewayAudio').click();await admin.waitForFunction(()=>document.querySelector('#gatewayActualOutput').textContent.includes('USB'));
    await admin.locator('#stopGatewayAudioTest').click();
    await scenario('audio_none');await admin.waitForFunction(()=>!document.querySelector('#gatewayAudioDevices li'));
    assert.equal(await admin.locator('#gatewayOutput').inputValue(),'a'.repeat(64));
    await shot(admin,'admin-gateway-no-device','#gatewayAudioSettings');
    await scenario('audio_restore');await admin.waitForFunction(()=>document.querySelector('#gatewayAudioDevices li'));
    await admin.locator('#gatewayOutput').selectOption('auto');await admin.locator('#saveGatewayAudio').click();
    await admin.waitForFunction(()=>document.querySelector('#gatewayAudioFeedback').textContent.includes('已保存'));
    if(directory)for(const command of ['lcd_home','lcd_settings','lcd_sound','lcd_outputs']){
      await scenario(command);const file=command.replaceAll('_','-')+'.webp';captured.push({file,sha256:hash(fs.readFileSync(path.join(directory,file)))});
    }
    await admin.locator('[data-setting=phoneMusicSettings]').click();await admin.locator('#ringtoneChoice').waitFor({state:'visible'});
    await shot(admin,'admin-settings','#settings');await shot(admin,'admin-ringtone','#phoneMusicSettings');assert.equal(await admin.locator('[data-tone]').count(),16);for(const button of await admin.locator('[data-tone]').all()){await button.click();await admin.waitForFunction(()=>document.querySelector('#musicStatus').textContent.includes('正在试听'));await admin.locator('#stopRingtone').click();}await shot(admin,'admin-ringtone-library','#phoneMusicSettings');
    for(const [width,height] of [[768,1024],[390,844],[844,390]]){await admin.setViewportSize({width,height});await noOverlap();const original=await admin.locator('#phoneLink').textContent();await admin.locator('#phoneLink').evaluate(node=>node.textContent='进入客厅平板话机模式 · 长标签测试');await noOverlap();await admin.locator('#phoneLink').evaluate((node,text)=>node.textContent=text,original);}
    await admin.setViewportSize({width:1024,height:768});await admin.evaluate(()=>document.body.style.zoom='2');await noOverlap();await admin.evaluate(()=>document.body.style.zoom='');
    await admin.locator('[data-setting=configForm]').click();await shot(admin,'admin-network','#configForm');await admin.locator('[data-setting=passwordForm]').click();await shot(admin,'admin-password','#passwordForm');await admin.locator('#backOverview').click();await shot(admin,'admin-journal','.journal');await admin.locator('#showSettings').click();await admin.locator('[data-setting=phoneMusicSettings]').click();
    await admin.locator('#ringtoneChoice').selectOption('marimba');await admin.locator('#ringDuration').selectOption('15');await admin.locator('#phoneMusicForm button.primary').click();
    await admin.waitForFunction(()=>document.querySelector('#musicStatus').textContent.includes('已保存'));
    // Upload a small original PCM tone through the administrator's actual browser importer.
    const wav=Buffer.alloc(44+16000);wav.write('RIFF');wav.writeUInt32LE(wav.length-8,4);wav.write('WAVEfmt ',8);wav.writeUInt32LE(16,16);wav.writeUInt16LE(1,20);wav.writeUInt16LE(1,22);wav.writeUInt32LE(8000,24);wav.writeUInt32LE(16000,28);wav.writeUInt16LE(2,32);wav.writeUInt16LE(16,34);wav.write('data',36);wav.writeUInt32LE(16000,40);
    for(let i=0;i<8000;i++)wav.writeInt16LE(Math.round(Math.sin(i/8000*2*Math.PI*660)*3000),44+i*2);
    await admin.locator('#ringtoneFile').setInputFiles({name:'synthetic-tone.wav',mimeType:'audio/wav',buffer:wav});await admin.locator('#uploadRingtone').click();
    await admin.waitForFunction(()=>document.querySelector('#musicStatus').textContent.includes('上传完成'));
    await admin.locator('#ringDuration').selectOption('30');await admin.locator('#phoneMusicForm button.primary').click();
    await admin.waitForFunction(()=>document.querySelector('#musicStatus').textContent.includes('已保存'));await shot(admin,'admin-custom-music','#phoneMusicSettings');
    await admin.locator('#previewRingtone').click();await admin.waitForFunction(()=>window.__soundEvents.some(e=>e.kind==='start' && e.loop));await admin.locator('#stopRingtone').click();
    // Enroll in this browser; enrollment deliberately invalidates its admin session.
    const page=await context.newPage();await page.goto(origin+'/phone');await page.locator('#enrollForm').waitFor({state:'visible'});
    await shot(page,'phone-enrollment','#setup');await page.locator('#adminPassword').fill('synthetic-phone-password');await page.locator('#enrollButton').click();
    await page.locator('#phone').waitFor({state:'visible'});await page.waitForFunction(()=>document.querySelector('#gatewayStatus').textContent.includes('已连接'));
    await page.locator('#hideControls').click();await page.locator('#soundIndicator').waitFor({state:'visible'});await shot(page,'phone-quiet-sound');await page.locator('#soundIndicator').click();
    await page.locator('#enableSound').click();await page.locator('#hideControls').click();await page.waitForFunction(()=>!document.querySelector('#message').textContent);
    await scenario('auto');await page.locator('#autoIndicator').waitFor({state:'visible'});await shot(page,'phone-quiet-auto');
    await context.setOffline(true);await page.locator('#connectionNotice').waitFor({state:'visible'});await shot(page,'phone-quiet-offline');await context.setOffline(false);await page.locator('#connectionNotice').waitFor({state:'hidden'});await scenario('auto_off');
    async function settledClock(){await page.waitForFunction(()=>{const face=document.querySelector('#clockFace');return face.style.getPropertyValue('--face-width')===face.clientWidth+'px'});}
    for(const style of ['editorial','digital','analog','nixie']){
      await page.locator('#wakeSurface').click();await page.locator('#clockStyle').selectOption(style);await page.locator('#secondsMode').selectOption(style==='analog'?'sweep':'step');await page.locator('#hideControls').click();
      assert.equal(await page.evaluate(()=>document.body.dataset.clock),style);
      if(style==='analog'){await page.emulateMedia({reducedMotion:'no-preference'});const previous=await page.locator('#secondHand').evaluate(node=>node.style.transform);await page.waitForFunction(previous=>document.querySelector('#secondHand').style.transform!==previous,previous);await page.emulateMedia({reducedMotion:'reduce'});}
      await shot(page,'clock-'+style);
      await page.setViewportSize({width:390,height:844});await settledClock();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.setViewportSize({width:1024,height:768});await settledClock();
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    }
    await page.locator('#wakeSurface').click();await page.locator('#secondsMode').selectOption('hidden');await page.locator('#hideControls').click();await shot(page,'clock-nixie-quiet');
    await page.reload();await page.locator('#phone').waitFor({state:'visible'});assert.equal(await page.locator('#clockStyle').inputValue(),'nixie');assert.equal(await page.locator('#secondsMode').inputValue(),'hidden');
    await page.locator('#showControls').click();await page.locator('#enableSound').click();await page.locator('#clockStyle').selectOption('editorial');await shot(page,'phone-preferences','#controls');
    assert.equal(await page.locator('#todayIncoming').textContent(),'8');
    assert.equal(await page.locator('#todayOpenings').textContent(),'4');
    await page.locator('#hideControls').click();await page.locator('#todayOpenings').focus();
    assert.ok((await page.locator('#todayOpenings').getAttribute('aria-label')).includes('协议确认'));await page.evaluate(()=>document.querySelector('#message').textContent='');await shot(page,'phone-statistics');
    await scenario('stats_unavailable');await page.waitForFunction(()=>document.querySelector('#todayIncoming').textContent==='—');
    await scenario('stats_restore');await page.waitForFunction(()=>document.querySelector('#todayIncoming').textContent==='8');
    await scenario('stats_large');await page.waitForFunction(()=>document.querySelector('#todayIncoming').textContent==='12345');
    for(const [width,height] of [[1024,768],[768,1024],[390,844],[844,390]]){
      await page.setViewportSize({width,height});
      for(const zoom of ['', '2']){
        await page.evaluate(zoom=>document.body.style.zoom=zoom,zoom);await settledClock();
        for(const id of ['todayIncoming','todayOpenings','showControls']){
          await page.locator('#'+id).focus();
          assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'focused '+id+' '+width+' '+zoom);
        }
      }
    }
    await page.evaluate(()=>document.body.style.zoom='');await page.setViewportSize({width:1024,height:768});
    await context.setOffline(true);await page.waitForFunction(()=>document.querySelector('#todayIncoming').textContent==='—');
    await context.setOffline(false);await scenario('stats_restore');await page.waitForFunction(()=>document.querySelector('#todayIncoming').textContent==='8');
    await page.locator('#wakeSurface').click();
    await page.locator('#hideControls').click();await page.locator('#wakeSurface').click();await page.locator('.recent summary').click();await shot(page,'phone-recent','#controls');await page.locator('.recent summary').click();assert.deepEqual((await scenario('inspect')).actions,[]);
    await page.locator('#panels button').first().click();await page.locator('#picture').waitFor({state:'visible'});await shot(page,'phone-preview');await page.locator('#hangup').click();await page.locator('#idle').waitFor({state:'visible'});
    await scenario('incoming');await page.locator('#picture').waitFor({state:'visible'});await page.waitForFunction(()=>window.__soundEvents.some(e=>e.kind==='stop' && e.remaining>20));
    await shot(page,'phone-incoming');
    const metrics=await page.evaluate(()=>{const p=document.querySelector('#picture'),r=p.getBoundingClientRect();return {width:r.width,height:r.height,ratio:p.naturalWidth/p.naturalHeight,fit:getComputedStyle(p).objectFit,w:innerWidth,h:innerHeight}});
    assert.equal(metrics.ratio,4/3);assert.equal(metrics.fit,'contain');assert.equal(metrics.width,metrics.w);assert.equal(metrics.height,metrics.h);
    await scenario('expire_ring');await page.waitForFunction(()=>document.querySelector('#soundStatus').textContent.includes('响铃已结束'));
    assert.equal(await page.locator('#hangup').isEnabled(),true);await shot(page,'phone-ring-ended');
    const count=await page.evaluate(()=>window.__soundEvents.filter(e=>e.kind==='start').length);
    await page.reload();await page.locator('#call').waitFor({state:'visible'}); // Expired call cannot ring again after reload.
    await page.evaluate(()=>window.__soundEvents=[]);
    await page.locator('#mute').click();
    await page.waitForFunction(()=>document.querySelector('#soundStatus').textContent.includes('响铃已结束'));
    assert.equal(await page.evaluate(()=>window.__soundEvents.filter(e=>e.kind==='start').length),0);
    assert.equal(await page.locator('#open').isEnabled(),true);
    await scenario('end');await page.locator('#idle').waitFor({state:'visible'});
    await page.locator('#wakeSurface').click();await page.locator('#enableSound').click();await page.locator('#hideControls').click();
    await scenario('incoming');await page.locator('#picture').waitFor({state:'visible'});await page.locator('#mute').click();assert.equal(await page.locator('#mute').textContent(),'铃声已静音');await shot(page,'phone-muted');
    await page.setViewportSize({width:768,height:1024});await shot(page,'phone-portrait');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.setViewportSize({width:390,height:844});await shot(page,'phone-mobile');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.setViewportSize({width:844,height:390});await shot(page,'phone-wide');assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.setViewportSize({width:1024,height:768});await scenario('video_stale');await page.locator('#picture').waitFor({state:'hidden'});await shot(page,'phone-stale-video');
    await context.setOffline(true);await page.waitForFunction(()=>document.querySelector('#open').disabled);await shot(page,'phone-offline');
    await context.setOffline(false);await scenario('end');await page.locator('#idle').waitFor({state:'visible'});
    await login(admin);await admin.locator('#showSettings').click();await admin.locator('[data-setting=phoneDevicesSettings]').click();await admin.locator('#deviceList li').waitFor({state:'visible'});await shot(admin,'admin-devices','#phoneDevicesSettings');
    await scenario('revoke');await page.locator('#setup').waitFor({state:'visible'});await shot(page,'phone-revoked');
    // Password rotation logs out through the same layout reset as explicit logout.
    await admin.locator('[data-setting=passwordForm]').click();
    await admin.locator('[name=current_password]').fill('synthetic-phone-password');
    await admin.locator('[name=new_password]').fill('synthetic-updated-password');
    await admin.locator('[name=confirm_password]').fill('synthetic-updated-password');
    await admin.locator('#passwordForm button').click();
    await admin.locator('#login').waitFor({state:'visible'});
    // Stay in the same document: navigation would conceal the hidden-overview regression.
    await admin.locator('#password').fill('synthetic-updated-password');
    await admin.locator('#loginForm button').click();
    await admin.locator('#overview').waitFor({state:'visible'});
    assert.equal(await admin.locator('.journal').isVisible(),true);
    assert.equal(await admin.locator('#settings').isVisible(),false);
    assert.equal(await admin.locator('#showSettings').getAttribute('aria-expanded'),'false');
    assert.deepEqual(errors,[]);assert.ok(count>0);
    if(directory){const sources={};for(const file of ['fermax/gateway_audio.py','fermax/display.py','fermax/web/gateway-audio.js','fermax/state.py','fermax/statistics.py','fermax/phone_preferences.py','fermax/api.py','fermax/web/app.js','fermax/web/ringtones.json','tests/phone_fixture.py','tests/phone_experience.cjs','fermax/web/phone.html','fermax/web/phone.css','fermax/web/phone.js','fermax/web/clock.js','fermax/web/ringtone.js','fermax/web/index.html','fermax/web/style.css','fermax/web/settings.js'])sources[file]=hash(fs.readFileSync(file));fs.writeFileSync(path.join(directory,'manifest.json'),JSON.stringify({kind:'synthetic-ui-demo',browser:engine,source_sha256:sources,images:captured},null,2)+'\n');}
    console.log(engine+' PASS: admin music upload/settings, four clocks, preferences, 4:3 full viewport, ring expiry, mute, portrait/mobile, stale video, offline and revoked demos');
  }finally{if(browser)await browser.close();fixture.stdin.end();const timer=setTimeout(()=>fixture.kill('SIGTERM'),3000);if(fixture.exitCode===null)await once(fixture,'exit');clearTimeout(timer);lines.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
