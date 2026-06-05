import { expect, test } from '@playwright/test'

import { getReplyAuditApi, listChatsApi, loginApi } from '../helpers/api'
import { loginAs } from '../helpers/auth'
import { operatorBCredentials, operatorCredentials } from '../helpers/env'
import { openChatById, sendChatMessage } from '../helpers/chat'

test.describe('E2E-6 reply audit on_behalf @requires-auth', () => {
  test.beforeEach(() => {
    test.skip(!operatorCredentials(), 'Set E2E_OPERATOR_A (owner) credentials')
    test.skip(!operatorBCredentials(), 'Set E2E_OPERATOR_B (colleague) credentials')
  })

  test('colleague reply is_on_behalf with correct owner and author', async ({ page, request }) => {
    const owner = operatorCredentials()!
    const colleague = operatorBCredentials()!

    const ownerSession = await loginApi(request, owner.email, owner.password)
    const colleagueSession = await loginApi(request, colleague.email, colleague.password)

    const ownerChats = await listChatsApi(request, ownerSession.accessToken, {
      card_owner_user_id: ownerSession.userId,
    })
    const groupChats = await listChatsApi(request, colleagueSession.accessToken, { sort: 'last_message_at_desc' })

    const target =
      ownerChats[0] ??
      groupChats.find((c) => c.card_owner_user_id === ownerSession.userId) ??
      groupChats[0]
    expect(target).toBeTruthy()
    expect(target.assigned_group_id).toBeTruthy()

    const replyText = `e2e-on-behalf-${Date.now()}`
    await loginAs(page, colleague)
    await openChatById(page, target.id)
    await sendChatMessage(page, replyText)

    const audit = await getReplyAuditApi(
      request,
      colleagueSession.accessToken,
      target.contact_id,
      target.assigned_group_id!,
    )
    const row = audit.find((item) => item.is_on_behalf) ?? audit[0]
    expect(row).toBeTruthy()
    expect(row.card_owner_user_id).toBe(ownerSession.userId)
    expect(row.author_user_id).toBe(colleagueSession.userId)
    expect(row.is_on_behalf).toBe(true)
  })
})
