import { expect, test } from '@playwright/test'

import { loginAsOperator, openFirstChat } from '../helpers/auth'

test.beforeEach(async ({ page }) => {
  test.skip(!process.env.E2E_EMAIL || !process.env.E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD')
  await loginAsOperator(page)
})

test('close lead button visible on open lead chat @requires-auth', async ({ page }) => {
  await openFirstChat(page)
  const closeBtn = page.getByRole('button', { name: /закрыть сделку/i })
  const visible = await closeBtn.isVisible().catch(() => false)
  if (!visible) {
    test.skip(true, 'No open lead on first chat — seed data required')
    return
  }
  await closeBtn.click()
  await expect(closeBtn).toBeHidden({ timeout: 15_000 })
})
