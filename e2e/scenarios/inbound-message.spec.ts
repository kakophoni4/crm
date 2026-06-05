import { expect, test } from '@playwright/test'

import { listChatsApi, loginApi, postBotEvent, pollUntil } from '../helpers/api'
import { loginAsOperatorA } from '../helpers/auth'
import { botCredentials, hasOperatorCredentials, operatorCredentials } from '../helpers/env'
import { openChatById, sendChatMessage, waitForChatListItem } from '../helpers/chat'

test.describe('E2E-2 inbound message @requires-auth @requires-bot', () => {
  test.beforeEach(() => {
    test.skip(!hasOperatorCredentials(), 'Set E2E_OPERATOR_A or E2E_EMAIL credentials')
    test.skip(!botCredentials(), 'Set E2E_BOT_CODE and E2E_BOT_SECRET')
  })

  test('contact writes via mock bot → operator sees chat and replies', async ({ page, request }) => {
    const operator = operatorCredentials()!
    const bot = botCredentials()!
    const inboundText = `e2e-inbound-${Date.now()}`
    const replyText = `e2e-reply-${Date.now()}`
    const telegramUserId = 88_200_000 + Math.floor(Math.random() * 99_999)

    await loginAsOperatorA(page)
    const session = await loginApi(request, operator.email, operator.password)

    const ingest = await postBotEvent(request, {
      botCode: bot.code,
      secret: bot.secret,
      telegramUserId,
      text: inboundText,
    })
    expect(ingest.status).toBe(202)

    const chat = await pollUntil(async () => {
      const items = await listChatsApi(request, session.accessToken, { sort: 'last_message_at_desc' })
      return (
        items.find(
          (item) =>
            item.last_message_preview?.includes(inboundText) ||
            item.contact_name.includes('E2E'),
        ) ?? null
      )
    })

    await waitForChatListItem(page, inboundText)
    await openChatById(page, chat.id)
    await sendChatMessage(page, replyText)

    const messages = page.locator('.message-list__row--out .message-list__text', { hasText: replyText })
    await expect(messages).toBeVisible()
    await expect(page.getByText('ошибка')).toHaveCount(0)
  })
})
