/* Run with Playwright installed; uses only a synthetic loopback fixture. */
const {spawn} = require('node:child_process');
const {createInterface} = require('node:readline');
const {once} = require('node:events');
const assert = require('node:assert/strict');
const browsers = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const fixture = spawn(process.env.PYTHON || 'python3', ['-m','tests.phone_fixture'], {stdio:['pipe','pipe','inherit']});
  const lines = createInterface({input:fixture.stdout});
  let browser;
  try {
    const [first] = await once(lines,'line'), {port} = JSON.parse(first);
    async function scenario(command) {
      const reply = once(lines,'line'); fixture.stdin.write(JSON.stringify({command})+'\n');
      return JSON.parse((await reply)[0]);
    }
    const engine = process.env.BROWSER_ENGINE || 'chromium';
    browser = await browsers[engine].launch({headless:true, executablePath:process.env.BROWSER_EXECUTABLE || undefined});
    const context = await browser.newContext({viewport:{width:1024,height:768},hasTouch:true});
    const page = await context.newPage(), errors = [];
    page.on('pageerror',error => errors.push(error.message));
    const origin = `http://127.0.0.1:${port}`;
    await page.clock.install();
    await page.goto(origin);
    await page.locator('#password').fill('synthetic-phone-password');
    await page.locator('#loginForm button').click();
    await page.locator('#workspace').waitFor({state:'visible'});
    await page.getByRole('link',{name:'平板话机模式'}).click();
    await page.locator('#enrollForm').waitFor({state:'visible'});
    await page.locator('#adminPassword').fill('synthetic-phone-password');
    await page.locator('#enrollButton').click();
    await page.locator('#phone').waitFor({state:'visible'});
    await page.waitForFunction(() => document.querySelector('#gatewayStatus').textContent.includes('已连接'));
    await page.locator('#enableSound').click();
    await page.locator('#hideControls').click();
    if (process.env.SCREENSHOT_DIR) await page.screenshot({path:process.env.SCREENSHOT_DIR+'/phone-idle.png',fullPage:true});
    // Exercise scheduled session rotation, without waiting twelve wall-clock minutes.
    for (let i = 0; i < 3; i++) {
      const renewal = page.waitForResponse(response => response.url().endsWith('/v1/phone/session') && response.status() === 200);
      await page.clock.fastForward(240001);
      await renewal;
      await page.waitForFunction(() => document.querySelector('#gatewayStatus').textContent.includes('已连接'));
    }
    // A wake touch reveals controls and sends no command.
    await page.locator('#wakeSurface').click();
    assert.deepEqual((await scenario('inspect')).actions,[]);
    await page.locator('#panels button').first().click();
    await page.locator('#call').waitFor({state:'visible'});
    await page.waitForFunction(() => document.querySelector('#callKind').textContent.includes('预览'));
    await page.locator('#picture').waitFor({state:'visible'});
    await page.locator('#hangup').click();
    await page.locator('#idle').waitFor({state:'visible'});
    await scenario('incoming');
    await page.locator('#call').waitFor({state:'visible'});
    await page.waitForFunction(() => !document.querySelector('#open').disabled);
    await page.locator('#mute').click();
    await scenario('hold_open');
    await page.locator('#open').click();
    await scenario('other_result');
    await page.waitForFunction(() => document.querySelector('#recent').textContent.includes('拒绝'));
    assert.match(await page.locator('#message').textContent(), /等待网关结果/);
    assert.equal(await page.locator('#open').isDisabled(),true);
    await scenario('complete_open');
    await page.waitForFunction(() => document.querySelector('#message').textContent.includes('确认开门'));
    assert.equal((await scenario('inspect')).actions.filter(action => action === 'open').length,1);
    if (process.env.SCREENSHOT_DIR) await page.screenshot({path:process.env.SCREENSHOT_DIR+'/phone-call.png',fullPage:true});
    // Browser refresh keeps the grant, but does not retain administrator access.
    await page.reload();
    await page.locator('#call').waitFor({state:'visible'});
    assert.equal((await context.request.get(origin+'/v1/config')).status(),401);
    await context.setOffline(true);
    await page.waitForFunction(() => document.querySelector('#open').disabled);
    await context.setOffline(false);
    await page.waitForFunction(() => document.querySelector('#gatewayStatus').textContent.includes('已连接'));
    assert.equal((await scenario('inspect')).actions.filter(action => action === 'open').length,1);
    await scenario('restart');
    await page.locator('#idle').waitFor({state:'visible'});
    await page.reload();
    await page.locator('#idle').waitFor({state:'visible'});
    await scenario('incoming');
    await page.locator('#call').waitFor({state:'visible'});
    await page.locator('#picture').waitFor({state:'visible'});
    await page.setViewportSize({width:390,height:844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),false);
    if (process.env.SCREENSHOT_DIR) await page.screenshot({path:process.env.SCREENSHOT_DIR+'/phone-portrait.png',fullPage:true});
    await scenario('revoke');
    await page.locator('#setup').waitFor({state:'visible'});
    assert.deepEqual(errors,[]);
    console.log(engine+' PASS: enroll, scoped auth, touch, preview, incoming, open once, request correlation, scheduled renewal, refresh, offline, restart, revoke, responsive layout');
  } finally {
    if (browser) await browser.close();
    fixture.stdin.end();
    const timeout = setTimeout(() => fixture.kill('SIGTERM'),3000);
    if (fixture.exitCode === null) await once(fixture,'exit');
    clearTimeout(timeout); lines.close();
  }
})().catch(error => { console.error(error); process.exitCode=1; });
