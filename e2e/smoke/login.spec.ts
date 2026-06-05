import { test } from '@playwright/test'

import { loginAsOperator, skipWithoutCredentials } from '../helpers/auth'

test('login shows chats @requires-auth', async ({ page }) => {
  test.skip(!process.env.E2E_EMAIL || !process.env.E2E_PASSWORD, 'Set E2E_EMAIL and E2E_PASSWORD')
  skipWithoutCredentials()
  await loginAsOperator(page)
})
