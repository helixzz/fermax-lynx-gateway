/* Fullscreen capability and enlarged-clock regressions against a loopback-only synthetic service. */
const {spawn}=require('node:child_process'),{once}=require('node:events'),{createInterface}=require('node:readline');
const assert=require('node:assert/strict'),browsers=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const child=spawn(process.env.PYTHON||'python3',['-m','tests.phone_fixture'],{stdio:['pipe','pipe','inherit']});
 const lines=createInterface({input:child.stdout});let browser;
 try{
  const {port}=JSON.parse((await once(lines,'line'))[0]),origin=`http://127.0.0.1:${port}`;
  async function scenario(command){const done=once(lines,'line');child.stdin.write(JSON.stringify({command})+'\n');return JSON.parse((await done)[0]);}
  browser=await browsers[process.env.BROWSER_ENGINE||'chromium'].launch({executablePath:process.env.BROWSER_EXECUTABLE||undefined});
  const context=await browser.newContext({viewport:{width:1024,height:768},hasTouch:true}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));await page.clock.install();
  await page.goto(origin);await page.locator('#password').fill('synthetic-phone-password');await page.locator('#loginForm button').click();await page.locator('#workspace').waitFor({state:'visible'});
  await page.goto(origin+'/phone');await page.locator('#adminPassword').fill('synthetic-phone-password');await page.locator('#enrollButton').click();await page.locator('#phone').waitFor({state:'visible'});
  // Model browser capabilities; real user clicks must cause the only requests.
  await page.evaluate(()=>{
   window.screenRequests=0;window.screenExits=0;window.screenActive=null;
   const root=document.documentElement;
   window.setScreenMode=mode=>{
    for(const name of ['requestFullscreen','webkitRequestFullscreen'])Object.defineProperty(root,name,{configurable:true,value:undefined});
    for(const name of ['fullscreenEnabled','webkitFullscreenEnabled'])Object.defineProperty(document,name,{configurable:true,value:true});
    for(const name of ['fullscreenElement','webkitFullscreenElement'])Object.defineProperty(document,name,{configurable:true,get:()=>window.screenActive});
    const request=function(){
     if(this!==root)throw Error('Wrong request receiver');
     if(navigator.userActivation && !navigator.userActivation.isActive)throw Error('Missing user gesture');
     window.screenRequests++;
     if(mode==='reject')return Promise.reject(Error('Synthetic denial'));
     window.screenActive=root;document.dispatchEvent(new Event(mode==='legacy'?'webkitfullscreenchange':'fullscreenchange'));
     return mode==='legacy'?undefined:Promise.resolve();
    };
    if(mode!=='unsupported')Object.defineProperty(root,mode==='legacy'?'webkitRequestFullscreen':'requestFullscreen',{configurable:true,value:request});
    for(const name of ['exitFullscreen','webkitExitFullscreen'])Object.defineProperty(document,name,{configurable:true,value:function(){if(this!==document)throw Error('Wrong exit receiver');window.screenExits++;window.screenActive=null;document.dispatchEvent(new Event('fullscreenchange'));return Promise.resolve();}});
    if(mode==='legacy')Object.defineProperty(document,'exitFullscreen',{configurable:true,value:undefined});
    document.dispatchEvent(new Event('fullscreenchange'));
   };
   window.setScreenMode('standard');
  });
  assert.equal(await page.evaluate(()=>screenRequests),0);
  for(const mode of ['standard','legacy']){
   await page.evaluate(mode=>setScreenMode(mode),mode);
   await page.locator('#fullscreenButton').click();assert.equal(await page.locator('#fullscreenButton').getAttribute('aria-pressed'),'true');
   await page.locator('#fullscreenButton').click();assert.equal(await page.locator('#fullscreenButton').getAttribute('aria-pressed'),'false');
  }
  assert.equal(await page.evaluate(()=>screenRequests),2);assert.equal(await page.evaluate(()=>screenExits),2);
  await page.evaluate(()=>{setScreenMode('standard');Object.defineProperty(document,'fullscreenEnabled',{configurable:true,value:false});document.dispatchEvent(new Event('fullscreenchange'));});await page.locator('#fullscreenButton').click();assert.equal(await page.evaluate(()=>screenRequests),2);assert.ok((await page.locator('#fullscreenHint').textContent()).includes('添加到主屏幕'));
  await page.evaluate(()=>setScreenMode('reject'));await page.locator('#fullscreenButton').click();assert.ok((await page.locator('#fullscreenHint').textContent()).includes('未允许'));
  await page.evaluate(()=>setScreenMode('unsupported'));await page.locator('#fullscreenButton').click();assert.ok((await page.locator('#fullscreenHint').textContent()).includes('添加到主屏幕'));assert.equal(await page.evaluate(()=>screenRequests),3);
  await page.evaluate(()=>{Object.defineProperty(navigator,'standalone',{configurable:true,value:true});document.dispatchEvent(new Event('fullscreenchange'));});assert.equal(await page.locator('#fullscreenButton').isVisible(),false);assert.ok((await page.locator('#fullscreenHint').textContent()).includes('独立窗口'));
  await page.evaluate(()=>{Object.defineProperty(navigator,'standalone',{configurable:true,value:false});setScreenMode('standard');});
  await page.locator('#fullscreenButton').click();await page.evaluate(()=>{screenActive=null;document.dispatchEvent(new Event('fullscreenchange'));});assert.equal(await page.locator('#fullscreenButton').getAttribute('aria-pressed'),'false');assert.equal(await page.evaluate(()=>screenRequests),4);
  // Actual rendered bounds, including hidden/shown seconds, tablet orientations and short landscape.
  const sizes=[];
  for(const style of ['editorial','digital','analog','nixie']){
   await page.locator('#clockStyle').selectOption(style);
   for(const seconds of ['hidden','step']){
    await page.locator('#secondsMode').selectOption(seconds);await page.locator('#hideControls').click();
    for(const viewport of [{width:1024,height:768},{width:768,height:1024},{width:1366,height:1024},{width:390,height:844},{width:844,height:390}]){
     await page.setViewportSize(viewport);await page.clock.runFor(1100);
     const bounds=await page.evaluate(()=>{const selector=document.body.dataset.clock==='analog'?'.analog-clock':document.body.dataset.clock==='nixie'?'.nixie-clock':'.numeric-clock';const r=document.querySelector(selector).getBoundingClientRect(),summary=document.querySelector('.idle-summary').getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height,summary:summary.top,overflow:document.documentElement.scrollWidth>innerWidth};});
     assert.equal(bounds.overflow,false,JSON.stringify({style,seconds,viewport,bounds}));assert.ok(bounds.left>=-1 && bounds.right<=viewport.width+1);assert.ok(bounds.bottom<=bounds.summary+1);
     if(viewport.width===1024 && seconds==='hidden'){if(style==='analog')assert.ok(bounds.height>460);else assert.ok(bounds.width>740);sizes.push({style,...bounds});}
    }
    await page.setViewportSize({width:1024,height:768});await page.locator('#showControls').click();
   }
  }
  assert.deepEqual((await scenario('inspect')).actions,[]);assert.deepEqual(errors,[]);
  console.log(JSON.stringify({engine:process.env.BROWSER_ENGINE||'chromium',result:'PASS: standard/legacy fullscreen, denial, absent API, external exit, standalone, gesture-only requests; clock bounds',sizes}));
 }finally{if(browser)await browser.close();child.stdin.end();const timer=setTimeout(()=>child.kill('SIGTERM'),3000);if(child.exitCode===null)await once(child,'exit');clearTimeout(timer);lines.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
