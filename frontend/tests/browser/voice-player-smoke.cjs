const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const assert=require('node:assert/strict'),path=require('node:path'),os=require('node:os')
;(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const page=await browser.newPage({viewport:{width:600,height:220}})
 await page.route('**/voice-preview',route=>route.fulfill({contentType:'text/html',body:`<html><body><div id="app"></div><script type="module">
 import {createApp,h} from '/node_modules/.vite/deps/vue.js';import Player from '/src/widgets/chat/VoiceMessagePlayer.vue';
 const samples=48000*3,b=new ArrayBuffer(44+samples*2),v=new DataView(b);const str=(p,s)=>[...s].forEach((c,i)=>v.setUint8(p+i,c.charCodeAt(0)));str(0,'RIFF');v.setUint32(4,36+samples*2,true);str(8,'WAVE');str(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,48000,true);v.setUint32(28,96000,true);v.setUint16(32,2,true);v.setUint16(34,16,true);str(36,'data');v.setUint32(40,samples*2,true);for(let i=0;i<samples;i++)v.setInt16(44+i*2,Math.sin(i/20)*Math.sin(i/9000)*8000,true);
 const blob=new Blob([b],{type:'audio/wav'});createApp({render:()=>h(Player,{src:URL.createObjectURL(blob),blob,loading:false,failed:false})}).mount('#app');
 </script><style>body{padding:35px;font-family:Arial;background:var(--app-surface)}#app{padding:16px;border:1px solid #8885;border-radius:18px;width:280px}</style></body></html>`}))
 await page.goto('http://127.0.0.1:5178/voice-preview')
 await page.waitForFunction(()=>document.querySelector('audio')?.duration===3)
 await page.getByRole('button',{name:'Воспроизвести голосовое',exact:true}).click()
 await page.waitForFunction(()=>document.querySelector('audio').currentTime>0)
 await page.getByRole('button',{name:'Пауза',exact:true}).click()
 await page.locator('.voice-meta button').click();assert.equal(await page.locator('audio').evaluate(n=>n.playbackRate),1.5)
 for(const theme of ['dark','light']){await page.evaluate(t=>{const s=document.documentElement.style;s.setProperty('--app-surface',t==='dark'?'#222a32':'#ffffff');s.setProperty('--app-text',t==='dark'?'#edf3fa':'#17212b');s.setProperty('--app-text-muted',t==='dark'?'#a7b6c3':'#617283');s.setProperty('--app-accent',t==='dark'?'#67b6fa':'#2488cc')},theme);await page.screenshot({path:path.join(os.tmpdir(),'voice-'+theme+'.png')})}
 console.log('PASS actual audio playback, pause, speed, themes')
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)})
