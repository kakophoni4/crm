import { expect, type Page } from '@playwright/test'

/** Open the first chat in the list (waits for list hydration). */
export async function openFirstChat(page: Page): Promise<void> {
  const firstChat = page.locator('.chats-page__list-item').first()
  await expect(firstChat).toBeVisible({ timeout: 30_000 })
  await firstChat.click()
  await expect(page.locator('.chats-page__message-scope')).toBeVisible({ timeout: 15_000 })
}

export async function openChatById(page: Page, chatId: number): Promise<void> {
  await page.goto(`/chats?chatId=${chatId}`)
  await expect(page.locator('.chats-page__message-scope')).toBeVisible({ timeout: 30_000 })
}

export async function sendChatMessage(page: Page, text: string): Promise<void> {
  const input = page.getByPlaceholder(/сообщение/i)
  await input.fill(text)
  await page.getByRole('button', { name: /^отправить$/i }).click()
  await expect(page.locator('.message-list__text', { hasText: text })).toBeVisible({
    timeout: 30_000,
  })
  await expect(page.getByText('отправка…')).toHaveCount(0)
}

export async function waitForChatListItem(
  page: Page,
  matcher: RegExp | string,
  timeoutMs = 60_000,
): Promise<void> {
  const item = page.locator('.chats-page__list-item').filter({ hasText: matcher })
  await expect(item.first()).toBeVisible({ timeout: timeoutMs })
}
