/* Loopback-only: auto visits, bounded notices and a stalled stream. */
const {spawn}=require('node:child_process'),{once}=require('node:events'),{createInterface}=require('node:readline');
const assert=require('node:assert/strict'),browsers=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const child=spawn(process.env.PYTHON||'python3',['-m','tests.phone_fixture'],{stdio:['pipe','pipe','inherit']});
 const lines=createInterface({input:child.stdout});let browser;
 try{
  const {port}=JSON.parse((await once(lines,'line'))[0]),origin=`http://127.0.0.1:${port}`;
  async function scenario(command){const done=once(lines,'line');child.stdin.write(JSON.stringify({command})+'\n');return JSON.parse((await done)[0]);}
  browser=await browsers[process.env.BROWSER_ENGINE||'chromium'].launch({executablePath:process.env.BROWSER_EXECUTABLE||undefined});
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(origin);await page.locator('#password').fill('synthetic-phone-password');await page.locator('#loginForm button').click();await page.locator('#workspace').waitFor({state:'visible'});
  await page.goto(origin+'/phone');await page.locator('#adminPassword').fill('synthetic-phone-password');await page.locator('#enrollButton').click();await page.locator('#phone').waitFor({state:'visible'});
  await scenario('auto');await scenario('incoming');await page.locator('#call').waitFor({state:'visible'});
  await scenario('auto_open');await page.waitForFunction(()=>document.querySelector('#message').textContent.includes('门口机已确认'));
  await page.waitForFunction(()=>!document.querySelector('#message').textContent);
  assert.equal(await page.locator('#call').isVisible(),true);
  await scenario('end');await page.locator('#idle').waitFor({state:'visible'});
  // Suppress stream data, keeping normal authenticated state reads available.
  await page.addInitScript(()=>{const original=window.fetch;window.fetch=(url,options)=>url==='/v1/phone/events'?new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))):original(url,options);});
  await page.reload();await scenario('incoming');await page.locator('#call').waitFor({state:'visible',timeout:15000});
  await page.request.post(origin+'/v1/login',{data:{password:'synthetic-phone-password'}});
  await page.waitForFunction(async()=> (await (await fetch('/v1/diagnostics')).json()).events.some(r=>r.kind==='phone_client'&&r.detail.event==='fallback_snapshot'));
  const records=await page.evaluate(async()=> (await (await fetch('/v1/diagnostics')).json()).events);
  assert.ok(records.some(r=>r.kind==='phone_client'&&r.detail.event==='fallback_snapshot'));
  assert.ok(records.some(r=>r.kind==='phone_client'&&r.detail.event==='call_rendered'));
  assert.deepEqual((await scenario('inspect')).actions,[]);assert.deepEqual(errors,[]);
  console.log('PASS auto call display, toast expiry, stalled stream fallback, client diagnostics; no controls');
 }finally{if(browser)await browser.close();child.stdin.end();const timer=setTimeout(()=>child.kill('SIGTERM'),3000);if(child.exitCode===null)await once(child,'exit');clearTimeout(timer);lines.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
