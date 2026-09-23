const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const assert = require('node:assert/strict')
const os = require('node:os'), path = require('node:path')
;(async () => {
 const browser = await chromium.launch({channel:'msedge',headless:true})
 try {
 const page = await browser.newPage({viewport:{width:1680,height:950}})
 const errors=[]; page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/*',async route=>{
 if(!['xhr','fetch'].includes(route.request().resourceType())) return route.continue()
 const p=new URL(route.request().url()).pathname
 let data={items:[],total:0}
 if(p.endsWith('/auth/me')) data={id:1,role:'admin',full_name:'Admin',permissions:['contacts.read','contacts.update','tasks.read'],group_ids:[1]}
 else if(p.endsWith('/opt-orders')) data={items:Array.from({length:4},(_,i)=>({id:i+1,lead_id:829,order_no:i+1,crm_id:'test',order_kind:'benik',status:'ready',payment_status:'unpaid',period_code:'2/26',total_volume:5170678,commission_base:'0',commission_adjustment:'0',commission_due:0,amount_paid:0,amount_remaining:0,volume_by_category:{},buyer:{inn:'1234567890',name:'ООО «Дом климата»'},source_filename:'Дом Климата.xlsx',created_at:'2026-09-24T00:00:00Z',payments:[],lines:Array.from({length:3},(_,j)=>({id:j+1,crm_id:'line',line_no:j+1,supplier:{inn:'1234567891',name:'ООО «ЭЛДЕКО»'},document_date:'2026-04-01',amount:1700000,vat_amount:0,amount_without_vat:1700000}))}))}
 await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})
 })
 for(const theme of ['dark','light']) {
 await page.addInitScript(t=>{localStorage.setItem('crm.auth.access_token','test');localStorage.setItem('crm-theme-mode',t)},theme)
 await page.goto(`${process.env.TEST_ORIGIN || 'http://127.0.0.1:5178'}/applications/829/1`)
 await page.locator('.opt-orders__tab').nth(3).waitFor()
 await page.waitForTimeout(400)
 assert.equal(await page.locator('.opt-orders__adjustment').count(),0)
 const box=await page.locator('.opt-orders__picker').evaluate(n=>({h:n.clientHeight,s:n.scrollHeight}))
 assert.ok(box.h>=box.s-1,JSON.stringify(box))
 assert.equal(await page.locator('.order-okved').evaluate(n=>getComputedStyle(n).display),'flex')
 await page.locator('.opt-orders__tab').nth(3).click()
 await page.waitForURL('**/829/4')
 await page.screenshot({path:path.join(os.tmpdir(),`crm-order-${theme}.png`)})
 }
 await page.setViewportSize({width:1024,height:768})
 await page.locator('.opt-orders__tab').first().click()
 await page.waitForURL('**/829/1')
 assert.ok(await page.locator('.opt-orders__workspace').evaluate(n=>n.scrollWidth<=n.clientWidth+1))
 assert.deepEqual(errors,[])
 console.log('PASS: four tabs visible, selection, zero adjustment, OKVED layout, light/dark')
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)})

