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
  await page.goto(origin);await page.locator('#password').fill('synthetic-phone-password');await page.locator('#loginForm button').click();await page.locator('#workspace').waitFor({state:'visible'});
  await page.goto(origin+'/phone');await page.locator('#adminPassword').fill('synthetic-phone-password');await page.locator('#enrollButton').click();await page.locator('#phone').waitFor({state:'visible'});
  await page.locator('#hideControls').click();assert.equal(await page.locator('.masthead').isVisible(),false);assert.equal(await page.locator('#idle .eyebrow').count(),0);
  await page.locator('#soundIndicator').waitFor({state:'visible'});assert.equal(await page.locator('#autoIndicator').isVisible(),false);assert.equal(await page.locator('.statusbar').isVisible(),false);
  await page.locator('#soundIndicator').click();assert.equal(await page.locator('#enableSound').evaluate(n=>n===document.activeElement),true);
  await page.locator('#enableSound').click();await page.locator('#soundIndicator').waitFor({state:'hidden'});
  await page.locator('#clockStyle').focus();await page.clock.runFor(21000);assert.equal(await page.locator('#controls').isVisible(),true);
  await page.keyboard.press('Escape');assert.equal(await page.locator('#showControls').evaluate(n=>n===document.activeElement),true);
  await page.keyboard.press('Enter');assert.equal(await page.locator('#hideControls').evaluate(n=>n===document.activeElement),true);
  await page.locator('.recent summary').focus();await page.keyboard.press('Tab');assert.equal(await page.locator('.manage-link').evaluate(n=>n===document.activeElement),true);
  await page.keyboard.press('Escape');await page.locator('#wakeSurface').click({position:{x:40,y:180}});await page.locator('#controlsBackdrop').click({position:{x:5,y:5}});assert.equal(await page.locator('#controls').isVisible(),false);
  assert.deepEqual((await scenario('inspect')).actions,[]);
  await scenario('auto');await page.locator('#autoIndicator').waitFor({state:'visible'});await page.locator('#autoIndicator').click();assert.equal(await page.locator('#autoStatus').isVisible(),true);await page.keyboard.press('Escape');
  await scenario('network_down');await page.locator('#connectionNotice').waitFor({state:'visible'});assert.ok((await page.locator('#connectionNotice').textContent()).includes('门禁'));
  await scenario('network_up');await page.locator('#connectionNotice').waitFor({state:'hidden'});
  await context.setOffline(true);await page.locator('#connectionNotice').waitFor({state:'visible'});assert.equal(await page.locator('#autoIndicator').isVisible(),false);
  await context.setOffline(false);await page.locator('#autoIndicator').waitFor({state:'visible'});
  await page.locator('#showControls').click();await page.locator('#volume').fill('0');await page.locator('#volume').dispatchEvent('input');await page.keyboard.press('Escape');await page.locator('#soundIndicator').waitFor({state:'visible'});assert.ok((await page.locator('#soundIndicator').getAttribute('aria-label')).includes('零'));
  await page.locator('#soundIndicator').click();assert.equal(await page.locator('#volume').inputValue(),'0');await page.locator('#volume').fill('35');await page.locator('#volume').dispatchEvent('input');
  await page.evaluate(()=>{window.originalPlay=LynxSound.prototype.play;LynxSound.prototype.play=async()=>{throw Error('synthetic playback refusal')};});
  await page.locator('#enableSound').click();await page.clock.runFor(2000);await page.keyboard.press('Escape');assert.ok((await page.locator('#soundIndicator').getAttribute('aria-label')).includes('受阻'));
  await page.evaluate(()=>LynxSound.prototype.play=window.originalPlay);await page.locator('#soundIndicator').click();await page.locator('#enableSound').click();await page.locator('#soundIndicator').waitFor({state:'hidden'});await page.keyboard.press('Escape');
  await page.reload();await page.locator('#phone').waitFor({state:'visible'});assert.equal(await page.locator('#controls').isVisible(),false);await page.locator('#soundIndicator').waitFor({state:'visible'});
  for(const style of ['editorial','digital','analog','nixie']){
   await page.locator('#showControls').click();await page.locator('#clockStyle').selectOption(style);await page.locator('#secondsMode').selectOption('step');await page.keyboard.press('Escape');
   for(const width of [1024,390]){
    await page.setViewportSize({width,height:768});await page.evaluate(()=>{document.body.style.zoom='2';window.dispatchEvent(new Event('resize'));});
    await page.clock.runFor(1100);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,style+' '+width+' 200%');
    await page.evaluate(()=>{document.body.style.zoom='';window.dispatchEvent(new Event('resize'));});
   }
   await page.setViewportSize({width:1024,height:768});
  }
  await page.locator('#showControls').click();await scenario('incoming');await page.locator('#call').waitFor({state:'visible'});assert.equal(await page.locator('#controls').isVisible(),false);assert.equal(await page.locator('#controlsBackdrop').isVisible(),false);assert.equal(await page.locator('#call').evaluate(n=>n===document.activeElement),true);
  await scenario('end');await page.locator('#idle').waitFor({state:'visible'});assert.equal(await page.locator('#showControls').evaluate(n=>n===document.activeElement),true);assert.deepEqual((await scenario('inspect')).actions,[]);assert.deepEqual(errors,[]);
  console.log((process.env.BROWSER_ENGINE||'chromium')+' PASS: quiet standby, contextual alerts, blocked sound, reconnect, zero volume, focus/timer/backdrop and no accidental controls');
 }finally{if(browser)await browser.close();child.stdin.end();const timer=setTimeout(()=>child.kill('SIGTERM'),3000);if(child.exitCode===null)await once(child,'exit');clearTimeout(timer);lines.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
