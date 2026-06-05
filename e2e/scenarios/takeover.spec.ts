import { expect, test } from '@playwright/test'

import { loginApi, startTakeoverApi } from '../helpers/api'
import { loginAs } from '../helpers/auth'
import { baseUrl, operatorCredentials, seniorCredentials } from '../helpers/env'
import { openFirstChat, sendChatMessage } from '../helpers/chat'

test.describe('E2E-4 senior takeover @requires-auth', () => {
  test.beforeEach(() => {
    test.skip(!operatorCredentials(), 'Set E2E_OPERATOR_A credentials')
    test.skip(!seniorCredentials(), 'Set E2E_SENIOR credentials')
  })

  test('senior joins chat, operator sees banner, senior releases', async ({ page, request }) => {
    const operator = operatorCredentials()!
    const senior = seniorCredentials()!

    await loginAs(page, operator)
    await openFirstChat(page)

    const chatIdMatch = page.url().match(/chatId=(\d+)/)
    const chatHeader = page.locator('.chats-page__chat-sub')
    await expect(chatHeader).toBeVisible()
    const headerText = await chatHeader.textContent()
    const chatIdFromHeader = headerText?.match(/#(\d+)/)?.[1]
    const chatId = Number(chatIdMatch?.[1] ?? chatIdFromHeader)
    expect(Number.isFinite(chatId)).toBeTruthy()

    const seniorSession = await loginApi(request, senior.email, senior.password)
    const seniorContext = await page.context().browser()!.newContext({ baseURL: baseUrl() })
    const seniorPage = await seniorContext.newPage()
    await loginAs(seniorPage, senior)
    await seniorPage.goto(`/chats?chatId=${chatId}`)
    await expect(seniorPage.locator('.chats-page__message-scope')).toBeVisible({ timeout: 30_000 })

    await startTakeoverApi(request, seniorSession.accessToken, chatId)

    await expect(page.getByText(/сейчас в чате руководитель/i)).toBeVisible({ timeout: 30_000 })

    const seniorMessage = `e2e-senior-${Date.now()}`
    await sendChatMessage(seniorPage, seniorMessage)
    await expect(page.locator('.message-list__text', { hasText: seniorMessage })).toBeVisible({
      timeout: 30_000,
    })

    await seniorPage.getByRole('button', { name: /^отключиться$/i }).click()
    await expect(page.getByText(/сейчас в чате руководитель/i)).toBeHidden({ timeout: 30_000 })

    await seniorContext.close()
  })
})
