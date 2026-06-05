import { expect, type Page } from '@playwright/test'

import type { Credentials } from './env'
import { operatorCredentials } from './env'

const hasLegacyCredentials = Boolean(process.env.E2E_EMAIL && process.env.E2E_PASSWORD)

export function skipWithoutCredentials(): void {
  if (!operatorCredentials()) {
    throw new Error('Set E2E_OPERATOR_A_EMAIL/PASSWORD or E2E_EMAIL/E2E_PASSWORD')
  }
}

/** Log in via UI and land on /chats (stable redirect for smoke specs). */
export async function loginAs(page: Page, credentials: Credentials): Promise<void> {
  await page.goto('/login?redirect=/chats')
  await page.getByLabel(/^email$/i).fill(credentials.email)
  await page.getByLabel(/^пароль$/i).fill(credentials.password)
  await page.getByRole('button', { name: /^войти$/i }).click()
  await expect(page).toHaveURL(/\/chats(?:\?|$)/, { timeout: 30_000 })
  await expect(page.locator('.chats-page__list, .chats-page__placeholder')).toBeVisible({
    timeout: 30_000,
  })
}

/** Smoke alias — uses E2E_EMAIL / E2E_PASSWORD. */
export async function loginAsOperator(page: Page): Promise<void> {
  if (!hasLegacyCredentials) {
    throw new Error('Set E2E_EMAIL and E2E_PASSWORD')
  }
  await loginAs(page, {
    email: process.env.E2E_EMAIL!,
    password: process.env.E2E_PASSWORD!,
  })
}

export async function loginAsOperatorA(page: Page): Promise<void> {
  const creds = operatorCredentials()
  if (!creds) throw new Error('Set E2E_OPERATOR_A_EMAIL/PASSWORD or E2E_EMAIL/E2E_PASSWORD')
  await loginAs(page, creds)
}

export { openFirstChat } from './chat'
