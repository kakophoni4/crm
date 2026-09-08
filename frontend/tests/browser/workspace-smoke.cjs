// Run against a local Vite server. Every API response is synthetic.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const assert = require('node:assert/strict')
const path = require('node:path')
const os = require('node:os')

async function main() {
  const browser = await chromium.launch({ channel: process.env.TEST_BROWSER_CHANNEL || 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1366, height: 768 } })
    const errors = []
    page.on('pageerror', (error) => errors.push(error.message))
    let role = 'user'
    let saved = null
    const order = {
      id: 1, order_id: 1, lead_id: 829, order_no: 1, manager_name: 'Менеджер', client_name: 'Тестовый клиент',
      client_inn: '3662221359', client_shop_name: 'ООО «Клиент»', period_code: '2025-Q4',
      volume: 1000000, due_amount: 13000, paid_amount: 0, remaining_amount: 13000, is_paid: false,
      lines: Array.from({ length: 15 }, (_, i) => ({
        id: i + 1, supplier_inn: `${7733430700 + i}`, supplier_name: `ООО «Лавка ${i + 1}»`,
        volume: 100000, due_amount: 1300, paid_amount: 0, remaining_amount: 1300,
        beneficiary_rate_percent: null, beneficiary_amount: 0, beneficiary_paid_amount: 0,
        actual_margin: 0, planned_margin: 1300, our_rate_percent: 1.3,
      })),
    }
    await page.addInitScript(() => localStorage.setItem('crm.auth.access_token', 'test-only'))
    await page.route('**/*', async (route) => {
      const request = route.request(), url = new URL(request.url()), p = url.pathname
      if (request.resourceType() !== 'xhr' && request.resourceType() !== 'fetch') return route.continue()
      // Vite modules use script requests; all API/network fetches below stay local.
      let data = { items: [], total: 0, unread: 0, blink: false }
      if (p.endsWith('/auth/me')) data = { id: 10, role, full_name: 'Тестовый пользователь', permissions: role === 'user' ? ['contacts.read', 'contacts.update', 'tasks.read'] : ['accounting.read', 'tasks.read'], group_id: 1, department_id: 1, group_ids: [1] }
      else if (p.endsWith('/opt-payment-register')) data = { items: [order], total: 1, total_volume_sum: order.volume, commission_due_sum: order.due_amount, amount_paid_sum: order.paid_amount }
      else if (p.includes('/settlements/')) { saved = request.postDataJSON(); data = { ok: true } }
      else if (p.endsWith('/lawyer-registry')) data = { items: [{ id: 1, full_name: 'Директор', shops: [{ id: 1, inn: '1111111111', name: 'Назначенная лавка', director_name: 'Директор', kind: 'priority', company_status: 'Действует' }], shop_count: 1 }], orphan_shops: [], pinned_shops: [], total_directors: 1, total_shops: 1, unread_alerts: 0 }
      else if (p.endsWith('/idle-banner')) data = { enabled: false }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
    })
    const origin = process.env.TEST_ORIGIN || 'http://127.0.0.1:5177'
    await page.goto(`${origin}/applications?tab=payments`)
    await page.getByRole('button', { name: 'Детали', exact: true }).click()
    await page.getByText('Получено от клиента', { exact: true }).waitFor()
    const content = page.locator('.applications-page__register-modal .n-card-content')
    const dimensions = await content.evaluate((node) => ({ client: node.clientHeight, scroll: node.scrollHeight, overflow: getComputedStyle(node).overflowY }))
    assert.ok(dimensions.scroll > dimensions.client)
    assert.equal(dimensions.overflow, 'auto')
    await content.evaluate((node) => { node.scrollTop = node.scrollHeight })
    assert.ok(await content.evaluate((node) => node.scrollTop > 0))
    await content.evaluate((node) => { node.scrollTop = 0 })
    await page.getByRole('button', { name: 'Заполнить условия', exact: true }).first().click()
    await page.locator('.settlement__form input').nth(0).fill('0.5')
    await page.locator('.settlement__form input').nth(1).fill('150')
    await page.getByRole('button', { name: 'Сохранить условия', exact: true }).click()
    await page.getByText('Условия бенефициара сохранены', { exact: true }).waitFor()
    assert.deepEqual(saved, { beneficiary_rate_percent: 0.5, beneficiary_paid_amount: 150, comment: null })
    await content.evaluate((node) => { node.scrollTop = 0 })
    await page.screenshot({ path: path.join(os.tmpdir(), 'crm-payment-desktop.png') })
    await page.setViewportSize({ width: 800, height: 600 })
    const box = await page.locator('.applications-page__register-modal').boundingBox()
    assert.ok(box.height <= 600 && box.width <= 800)
    await page.screenshot({ path: path.join(os.tmpdir(), 'crm-payment-small.png') })
    await page.setViewportSize({ width: 1366, height: 768 })
    role = 'accountant'
    await page.goto(`${origin}/registry?inn=1111111111`)
    await page.getByRole('heading', { name: 'Назначенная лавка', exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: 'Новая лавка', exact: true }).count(), 0)
    assert.equal(await page.locator('.assigned-shops input').count(), 0)
    await page.screenshot({ path: path.join(os.tmpdir(), 'crm-assigned-shops.png') })
    assert.deepEqual(errors, [])
    console.log('PASS: payment form save, internal scrolling, small viewport, accountant read-only cards; no page errors')
    console.log('Screenshots: ' + os.tmpdir())
  } finally { await browser.close() }
}
main().catch((error) => { console.error(error); process.exitCode = 1 })
