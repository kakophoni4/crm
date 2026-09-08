const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright')
const assert = require('node:assert/strict')
const path = require('node:path')
const os = require('node:os')

async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true })
  try {
    const page = await browser.newPage({ viewport: { width: 1366, height: 768 } })
    const errors = []
    page.on('pageerror', e => { errors.push(e.message); console.log('PAGE_ERROR',e.message) })
    let role = 'accountant', cardPatch, okvedPatch
    const unit = { id: 1, unit_id: 1, inn: '1111111111', name: 'Тестовая лавка', category_code: 'TECH', is_active: true, period_codes: ['2026-Q2'], accountant_user_id: 10, accountant_full_name: 'Бухгалтер', lawyer_shop_id: 1 }
    const card = { id: 1, inn: unit.inn, name: unit.name, fns: '1234', registered_at: '2020-01-01', received_at: '2026-09-01', director_name: 'Директор', dirovod: 'Ответственный' }
    const order = { id: 1, lead_id: 829, order_no: 1, crm_id: 'test', status: 'draft', payment_status: 'unpaid', period_code: '2026-Q2', buyer: { inn: '2222222222', name: 'Покупатель' }, buyer_okved: null, lines: [], payments: [], commission_history: [], volume_by_category: {}, total_volume: 0, commission_base: 0, commission_adjustment: 0, commission_due: 0, amount_paid: 0, amount_remaining: 0, vat_rate_percent: 22, created_at: '2026-09-08T12:00:00Z' }
    await page.addInitScript(() => localStorage.setItem('crm.auth.access_token', 'test-only'))
    await page.route('**/*', async route => {
      const req = route.request(), p = new URL(req.url()).pathname
      if (!['xhr', 'fetch'].includes(req.resourceType())) return route.continue()
      let data = { items: [], total: 0, unread: 0, blink: false }
      if (p.endsWith('/auth/me')) data = { id: 10, role, full_name: 'Тест', permissions: role === 'user' ? ['contacts.read', 'contacts.update', 'tasks.read'] : ['accounting.read', 'tasks.read'], group_id: 1, department_id: 1, group_ids: [1] }
      else if (p.endsWith('/accounting/units')) data = { items: [unit], is_chief: false }
      else if (p.endsWith('/assignments/units')) data = { items: [unit], accountants: [] }
      else if (p.endsWith('/units/1/card')) {
        if (req.method() === 'PATCH') { cardPatch = req.postDataJSON(); Object.assign(card, cardPatch) }
        data = card
      } else if (p.endsWith('/leads/829/opt-orders')) data = { items: [order] }
      else if (p.endsWith('/opt-orders/1/okved')) { okvedPatch = req.postDataJSON(); Object.assign(order, okvedPatch); data = okvedPatch }
      else if (p.endsWith('/idle-banner')) data = { enabled: false }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(data) })
    })
    await page.goto('http://127.0.0.1:5177/accounting')
    await page.screenshot({ path: path.join(os.tmpdir(), 'crm-accounting-debug.png') })
    await page.getByText('Лавки', { exact: true }).click()
    await page.getByRole('button', { name: 'Карточка лавки', exact: true }).click()
    const fns = page.locator('.n-form-item').filter({ has: page.locator('.n-form-item-label', { hasText: /^ФНС$/ }) }).locator('input')
    await fns.fill('5678')
    await page.getByRole('button', { name: 'Сохранить', exact: true }).click()
    await page.getByText('Лавка сохранена', { exact: true }).waitFor()
    assert.deepEqual(cardPatch, { fns: '5678' })
    assert.equal(await page.getByRole('button', { name: 'Удалить', exact: true }).count(), 0)
    await page.getByRole('button', { name: 'Карточка лавки', exact: true }).click()
    assert.equal(await fns.inputValue(), '5678')
    await page.setViewportSize({ width: 390, height: 700 })
    await page.screenshot({ path: path.join(os.tmpdir(), 'crm-shop-mobile.png') })
    await page.getByRole('button', { name: 'Отмена', exact: true }).click()
    await page.setViewportSize({ width: 1366, height: 768 })
    role = 'user'
    await page.goto('http://127.0.0.1:5177/applications/829/1')
    const okved = page.getByRole('textbox', { name: 'ОКВЭД покупателя', exact: true })
    await okved.fill('47.11')
    await page.locator('.order-okved').getByRole('button', { name: 'Сохранить' }).click()
    await page.getByText('ОКВЭД сохранён', { exact: true }).waitFor()
    assert.deepEqual(okvedPatch, { buyer_okved: '47.11' })
    await page.reload()
    await okved.waitFor()
    assert.equal(await okved.inputValue(), '47.11')
    await okved.fill('')
    await page.locator('.order-okved').getByRole('button', { name: 'Сохранить' }).click()
    await page.getByText('ОКВЭД сохранён', { exact: true }).waitFor()
    assert.deepEqual(okvedPatch, { buyer_okved: null })
    assert.deepEqual(errors, [])
    console.log('PASS: accountant edits shared card, sends only changed fields, mobile form, order OKVED saves/reloads/clears; no page errors')
  } finally { await browser.close() }
}
main().catch(e => { console.error(e); process.exit(1) })
