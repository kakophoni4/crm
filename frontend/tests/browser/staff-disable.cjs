const {chromium}=require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const assert=require('node:assert/strict')
;(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true})
 try{
 for(const theme of ['light','dark']){
 const page=await browser.newPage({viewport:{width:1000,height:800}})
 const errors=[];page.on('pageerror',e=>errors.push(e.message))
 const users=['admin','accountant','lawyer','senior','group_senior','user'].map((role,i)=>({id:i+1,role,username:'u'+i,full_name:'Employee '+i,status:'active',group_ids:[],department_id:null,group_id:null}))
 let removed=[]
 await page.addInitScript(t=>{localStorage.setItem('crm.auth.access_token','test');localStorage.setItem('crm-theme-mode',t)},theme)
 await page.route('**/*',async route=>{
 const req=route.request(),p=new URL(req.url()).pathname
 if(!['xhr','fetch'].includes(req.resourceType()))return route.continue()
 let data={items:[],total:0}
 if(p.endsWith('/auth/me'))data={...users[0],permissions:['users.read','users.deactivate']}
 else if(p.endsWith('/users'))data={items:users}
 else if(p.endsWith('/remove')){const id=Number(p.split('/').at(-2));removed.push(id);users.find(u=>u.id===id).status='disabled';data=users.find(u=>u.id===id)}
 await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)})
 })
 await page.goto((process.env.TEST_ORIGIN||'http://127.0.0.1:5178')+'/admin/users')
 await page.getByRole('button',{name:'Отключить',exact:true}).first().waitFor()
 assert.equal(await page.locator('.n-data-table').getByRole('button',{name:'Отключить',exact:true}).count(),5)
 await page.getByRole('button',{name:'Изменить',exact:true}).nth(1).click()
 await page.getByRole('button',{name:'Отключить пользователя',exact:true}).click()
 assert.deepEqual(removed,[])
 await page.getByText('История сохранится.',{exact:false}).waitFor()
 await page.locator('.n-popover').getByRole('button',{name:'Отмена',exact:true}).click()
 assert.deepEqual(removed,[])
 await page.getByRole('button',{name:'Отключить пользователя',exact:true}).click()
 await page.locator('.n-popover').getByRole('button',{name:'Отключить',exact:true}).click()
 await page.getByText('отключён',{exact:true}).waitFor()
 assert.deepEqual(removed,[2])
 assert.equal(await page.locator('.n-data-table').getByRole('button',{name:'Отключить',exact:true}).count(),4)
 assert.deepEqual(errors,[])
 await page.close()
 }
 console.log('PASS: staff role buttons, protected admin, edit dialog, cancel and confirmed disable, both themes')
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1})
