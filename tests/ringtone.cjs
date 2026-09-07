/* Deterministic audio lifecycle tests; no device, server or real sound output. */
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
(async()=>{
  let now=0;const window={};vm.runInNewContext(fs.readFileSync('fermax/web/ringtone.js','utf8'),{window,performance:{now:()=>now},setTimeout,clearTimeout,AbortController});
  const sound=new window.LynxSound(),events=[];
  sound.context={state:'running',currentTime:100,createBufferSource(){return {connect(){},disconnect(){},start(){events.push(['start',this.loop])},stop(when){events.push(['stop',when])}}},createGain(){return {gain:{value:0},connect(){},disconnect(){}}},destination:{}};
  sound.prepare=async()=>{now+=3000;return {duration:2}};
  await sound.play({ringtone:'custom'},30,.4);
  assert.deepEqual(events,[['start',true],['stop',127]]); // Loading consumes the same deadline.
  sound.volume(5);assert.equal(sound.gain.gain.value,1);sound.stop();assert.equal(sound.mode,null);
  events.length=0;let reject;
  sound.prepare=()=>new Promise((_,fail)=>{reject=fail});
  const pending=sound.play({},15,.5);assert.equal(sound.mode,'call');sound.stop();reject(Error('late network failure'));await pending;
  assert.equal(events.length,0); // Cancelled loads cannot trigger a later playback/fallback.
  sound.prepare=async()=>{now+=16000;return {duration:1}};await sound.play({},15,.5);assert.equal(events.length,0);assert.equal(sound.mode,null);
  console.log('PASS: audio looping, absolute remaining duration, cancellation, late failure and volume bounds');
})().catch(e=>{console.error(e);process.exitCode=1});

// Render every original score: bounded buffers, clean loop edges and distinct output.
{
  const catalog=JSON.parse(fs.readFileSync('fermax/web/ringtones.json','utf8'));
  const window={LynxRingtones:catalog};vm.runInNewContext(fs.readFileSync('fermax/web/ringtone.js','utf8'),{window});
  const sound=new window.LynxSound();sound.context={createBuffer(channels,length,rate){const samples=new Float32Array(length);return {duration:length/rate,getChannelData:()=>samples}}};
  assert.equal(catalog.length,16);assert.equal(new Set(catalog.map(track=>track.id)).size,16);
  const hashes=new Set();
  for(const track of catalog){const buffer=sound.builtin(track.id),samples=buffer.getChannelData(0);assert.ok(buffer.duration>2&&buffer.duration<15);let peak=0;for(const sample of samples){assert.ok(Number.isFinite(sample));peak=Math.max(peak,Math.abs(sample));}assert.ok(peak>.25&&peak<.27);assert.equal(samples[0],0);assert.equal(samples[samples.length-1],0);hashes.add(require('crypto').createHash('sha256').update(Buffer.from(samples.buffer)).digest('hex'));}
  assert.equal(hashes.size,16);console.log('PASS: 16 distinct offline scores, finite samples, bounded duration, matched peaks and silent loop edges');
}
