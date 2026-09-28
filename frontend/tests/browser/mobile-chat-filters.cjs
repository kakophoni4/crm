const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const assert=require('node:assert/strict')
const os=require('node:os'),path=require('node:path')
;(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true})
 try {
 for(const theme of ['light','dark']) {
 const page=await browser.newPage({viewport:{width:390,height:844}})
 const errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.addInitScript(t=>{localStorage.setItem('crm.auth.access_token','test');localStorage.setItem('crm-theme-mode',t)},theme)
 let query
 await page.route('**/*',async route=>{
 const req=route.request(),url=new URL(req.url()),p=url.pathname
 if(!['fetch','xhr'].includes(req.resourceType()))return route.continue()
 let data={items:[],total:0,unread:0,next_cursor:null}
 if(p.endsWith('/auth/me'))data={id:10,role:'user',full_name:'Tester',permissions:['chats.read','chats.write'],group_id:1,group_ids:[1],department_id:1}
 else if(p.endsWith('/bots'))data={items:[{id:2,name:'Тестовый бот',is_active:true,channel:'telegram'}]}
 else if(p.endsWith('/statuses'))data={items:[{id:7,code:'new',kind:'lead_pipeline',label:'Новая',is_active:true}]}
 else if(p.endsWith('/chats')){query=url.searchParams;data={items:[],next_cursor:null}}
 await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})
 })
 await page.goto((process.env.TEST_ORIGIN||'http://127.0.0.1:5178')+'/chats')
 await page.getByRole('button',{name:'Фильтры и сортировка',exact:true}).waitFor()
 assert.equal(await page.getByRole('button',{name:'Фильтры и сортировка',exact:true}).getAttribute('aria-expanded'),'true')
 const panel=page.locator('#chat-list-filters');await panel.waitFor({state:'visible'})
 await panel.locator('.n-select').nth(0).click()
 await page.getByText('Тестовый бот',{exact:true}).click()
 await page.waitForTimeout(300);assert.equal(query.get('bot_id'),'2')
 await panel.getByRole('switch',{name:'Только непрочитанные',exact:true}).click()
 await panel.locator('.n-select').last().click()
 await page.getByText('Новые чаты',{exact:true}).click()
 await page.waitForTimeout(300);assert.equal(query.get('sort'),'created_at_desc');assert.equal(query.get('unread_only'),'true')
 await panel.locator('.n-select').nth(1).click()
 await page.getByText('Новая',{exact:true}).click()
 await panel.getByRole('switch',{name:'Только с открытой сделкой',exact:true}).click()
 await page.waitForTimeout(300);assert.equal(query.get('lead_status_id'),'7');assert.equal(query.get('lead_open_only'),'true')
 await page.getByRole('button',{name:'Свернуть фильтры',exact:true}).click()
 assert.equal(await panel.isVisible(),false)
 await page.getByRole('button',{name:'Фильтры и сортировка · 5',exact:true}).click()
 await page.screenshot({path:path.join(os.tmpdir(),'crm-mobile-filters-'+theme+'.png')})
 assert.ok(await page.locator('body').evaluate(n=>n.scrollWidth<=window.innerWidth))
 await panel.getByRole('button',{name:'Сбросить',exact:true}).click()
 await page.waitForTimeout(300);assert.equal(query.get('bot_id'),null);assert.equal(query.get('unread_only'),null);assert.equal(query.get('sort'),'last_message_at_desc')
 await page.setViewportSize({width:1440,height:900});assert.equal(await panel.isVisible(),true)
 assert.deepEqual(errors,[])
 await page.close()
 }
 console.log('PASS: mobile filters, query parameters, reset, collapse, desktop parity, light/dark')
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1})
