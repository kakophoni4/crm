import { expect, test } from '@playwright/test'

import { getContactApi, listChatsApi, loginApi } from '../helpers/api'
import { loginAs } from '../helpers/auth'
import {
  operatorBCredentials,
  operatorCredentials,
} from '../helpers/env'
import { openFirstChat } from '../helpers/chat'

test.describe('E2E-3 contact transfer @requires-auth', () => {
  test.beforeEach(() => {
    test.skip(!operatorCredentials(), 'Set E2E_OPERATOR_A credentials')
    test.skip(!operatorBCredentials(), 'Set E2E_OPERATOR_B credentials')
  })

  test('immediate transfer changes card owner to user_b', async ({ page, request }) => {
    const userA = operatorCredentials()!
    const userB = operatorBCredentials()!

    const sessionB = await loginApi(request, userB.email, userB.password)
    const toUserId = sessionB.userId

    await loginAs(page, userA)
    await openFirstChat(page)

    const sessionA = await loginApi(request, userA.email, userA.password)
    const chatsBefore = await listChatsApi(request, sessionA.accessToken)
    const activeChat = chatsBefore[0]
    expect(activeChat?.assigned_group_id).toBeTruthy()

    await page.getByRole('button', { name: /передать карточку/i }).click()
    await page.getByPlaceholder(/ID пользователя/i).fill(String(toUserId))
    await page.getByRole('button', { name: /передать карточку/i }).last().click()
    await expect(page.getByText(/карточка назначена/i)).toBeVisible({ timeout: 15_000 })

    const contact = await getContactApi(request, sessionA.accessToken, activeChat.contact_id)
    const groupId = activeChat.assigned_group_id!

    const ownership = contact.group_ownership.find((row) => row.group_id === groupId)
    expect(ownership?.owner_user_id).toBe(toUserId)
  })
})
