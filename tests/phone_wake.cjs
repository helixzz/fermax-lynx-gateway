/* Quiet standby state/keyboard regressions against a loopback-only synthetic service. */
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
  await context.addInitScript(()=>{
   window.wakeCalls=0;window.wakeReleases=0;window.wakeMode='normal';window.wakeLocks=[];
   window.makeWake=()=>{const lock=new EventTarget();lock.released=false;lock.release=async()=>{if(!lock.released){lock.released=true;wakeReleases++;lock.dispatchEvent(new Event('release'));}};wakeLocks.push(lock);return lock;};
   window.mockWake={request:async type=>{if(type!=='screen')throw Error('Wrong wake type');wakeCalls++;if(wakeMode==='deny')throw Error('Synthetic denial');if(wakeMode==='pending')return new Promise((resolve,reject)=>{window.resolveWake=()=>resolve(makeWake());window.rejectWake=()=>reject(Error('Late denial'));});return makeWake();}};
   Object.defineProperty(navigator,'wakeLock',{configurable:true,value:mockWake});
   window.setHidden=value=>{Object.defineProperty(document,'hidden',{configurable:true,value});document.dispatchEvent(new Event('visibilitychange'));};
  });
  await page.goto(origin);await page.locator('#password').fill('synthetic-phone-password');await page.locator('#loginForm button').click();await page.locator('#workspace').waitFor({state:'visible'});
  await page.goto(origin+'/phone');await page.locator('#adminPassword').fill('synthetic-phone-password');await page.locator('#enrollButton').click();await page.locator('#phone').waitFor({state:'visible'});
  await page.waitForFunction(()=>document.querySelector('#wakeHint').textContent.includes('已保持亮屏'));
  assert.equal(await page.evaluate(()=>wakeCalls),1);assert.ok(await page.locator('#enableSound').isVisible());
  await page.locator('#wakeButton').click();assert.equal(await page.evaluate(()=>wakeReleases),1);
  await page.clock.runFor(4000);assert.equal(await page.evaluate(()=>wakeCalls),1);
  await page.locator('#wakeButton').click();await page.waitForFunction(()=>wakeCalls===2);assert.equal(await page.locator('#wakeButton').getAttribute('aria-pressed'),'true');
  await page.evaluate(()=>setHidden(true));await page.waitForFunction(()=>wakeReleases===2);await page.evaluate(()=>setHidden(false));await page.waitForFunction(()=>wakeCalls===3);
  await page.evaluate(()=>wakeLocks[wakeLocks.length-1].release());await page.clock.runFor(10000);assert.equal(await page.evaluate(()=>wakeCalls),3);assert.ok((await page.locator('#wakeHint').textContent()).includes('系统已释放'));
  await page.locator('#wakeButton').click();await page.waitForFunction(()=>wakeCalls===4);
  await page.locator('#wakeButton').click();await page.evaluate(()=>wakeMode='pending');await page.locator('#wakeButton').click();assert.equal(await page.evaluate(()=>wakeCalls),5);
  await page.evaluate(()=>{window.dispatchEvent(new Event('online'));window.dispatchEvent(new Event('pageshow'));});assert.equal(await page.evaluate(()=>wakeCalls),5);
  await page.evaluate(()=>{setHidden(true);setHidden(false);wakeMode='normal';resolveWake();});await page.waitForFunction(()=>wakeCalls===6);assert.equal(await page.evaluate(()=>wakeLocks.filter(x=>!x.released).length),1);
  await page.locator('#wakeButton').click();await page.evaluate(()=>wakeMode='deny');await page.locator('#wakeButton').click();await page.waitForFunction(()=>document.querySelector('#wakeHint').textContent.includes('被拒绝'));await page.clock.runFor(6000);assert.equal(await page.evaluate(()=>wakeCalls),7);
  await page.evaluate(()=>wakeMode='normal');await page.locator('#wakeButton').click();await page.waitForFunction(()=>wakeCalls===8);
  await page.evaluate(()=>window.dispatchEvent(new Event('pagehide')));assert.equal(await page.evaluate(()=>wakeLocks.filter(x=>!x.released).length),0);await page.evaluate(()=>window.dispatchEvent(new Event('pageshow')));await page.waitForFunction(()=>wakeCalls===9);
  await page.locator('#wakeButton').click();await page.evaluate(()=>{Object.defineProperty(window,'isSecureContext',{configurable:true,value:false});});await page.locator('#wakeButton').click();assert.ok((await page.locator('#wakeHint').textContent()).includes('HTTPS'));assert.equal(await page.locator('#wakeButton').isVisible(),false);assert.equal(await page.evaluate(()=>wakeCalls),9);
  await page.evaluate(()=>{Object.defineProperty(window,'isSecureContext',{configurable:true,value:true});Object.defineProperty(navigator,'wakeLock',{configurable:true,value:undefined});window.dispatchEvent(new Event('online'));});assert.ok((await page.locator('#wakeHint').textContent()).includes('不支持'));assert.equal(await page.evaluate(()=>wakeCalls),9);
  await page.evaluate(()=>{Object.defineProperty(navigator,'wakeLock',{configurable:true,value:mockWake});window.dispatchEvent(new Event('online'));});await page.waitForFunction(()=>wakeCalls===10);
  await page.locator('#wakeButton').click();await page.evaluate(()=>wakeMode='pending');await page.locator('#wakeButton').click();assert.equal(await page.evaluate(()=>wakeCalls),11);
  await page.locator('#wakeButton').click();await page.locator('#wakeButton').click();assert.equal(await page.evaluate(()=>wakeCalls),11);await page.evaluate(()=>{wakeMode='normal';resolveWake();});await page.waitForFunction(()=>wakeCalls===12);assert.equal(await page.evaluate(()=>wakeLocks.filter(x=>!x.released).length),1);
  await page.locator('#wakeButton').click();await page.evaluate(()=>wakeMode='pending');await page.locator('#wakeButton').click();assert.equal(await page.evaluate(()=>wakeCalls),13);await page.evaluate(()=>{setHidden(true);setHidden(false);wakeMode='normal';rejectWake();});await page.waitForFunction(()=>wakeCalls===14);assert.ok((await page.locator('#wakeHint').textContent()).includes('已保持亮屏'));
  await page.locator('#logout').click();await page.locator('#setup').waitFor({state:'visible'});assert.equal(await page.evaluate(()=>wakeLocks.filter(x=>!x.released).length),0);assert.deepEqual((await scenario('inspect')).actions,[]);assert.deepEqual(errors,[]);
  console.log((process.env.BROWSER_ENGINE||'chromium')+' PASS: automatic independent wake lock, stop/retry, visibility and page lifecycle, late/concurrent requests, denial, external release, HTTP/unsupported, logout');
 }finally{if(browser)await browser.close();child.stdin.end();const timer=setTimeout(()=>child.kill('SIGTERM'),3000);if(child.exitCode===null)await once(child,'exit');clearTimeout(timer);lines.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
