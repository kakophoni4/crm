import { expect, test } from '@playwright/test'

import { getContactHistoryApi, listChatsApi, loginApi } from '../helpers/api'
import { loginAsOperatorA } from '../helpers/auth'
import { hasOperatorCredentials, operatorCredentials } from '../helpers/env'
import { openFirstChat } from '../helpers/chat'

test.describe('E2E-5 contact edit history @requires-auth', () => {
  test.beforeEach(() => {
    test.skip(!hasOperatorCredentials(), 'Set E2E_OPERATOR_A or E2E_EMAIL credentials')
  })

  test('edit contact field and see history entry', async ({ page, request }) => {
    const operator = operatorCredentials()!
    const session = await loginApi(request, operator.email, operator.password)

    await loginAsOperatorA(page)
    await openFirstChat(page)

    const chats = await listChatsApi(request, session.accessToken)
    const contactId = chats[0]?.contact_id
    expect(contactId).toBeTruthy()

    const newPhone = `+7999${String(Date.now()).slice(-7)}`
    await page.goto(`/contacts/${contactId}`)
    await expect(page.getByRole('tab', { name: /^карточка$/i })).toBeVisible({ timeout: 30_000 })

    const phoneInput = page.locator('.contact-detail__form').getByRole('textbox').nth(1)
    await phoneInput.fill(newPhone)
    await page.getByRole('button', { name: /^сохранить$/i }).click()
    await expect(page.getByText(/^сохранено$/i)).toBeVisible({ timeout: 15_000 })

    await page.getByRole('tab', { name: /^история$/i }).click()
    await expect(page.locator('.n-data-table')).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('cell', { name: 'phone' })).toBeVisible()
    await expect(page.getByRole('cell', { name: newPhone })).toBeVisible()

    const history = await getContactHistoryApi(request, session.accessToken, contactId)
    const row = history.find((item) => item.field_name === 'phone' && String(item.new_value) === newPhone)
    expect(row).toBeTruthy()
    expect(row?.changed_by).toBe(session.userId)
  })
})
