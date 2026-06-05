import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

import { expect, test } from '@playwright/test'

import { loginAsOperatorA } from '../helpers/auth'
import { hasOperatorCredentials } from '../helpers/env'
import { openFirstChat } from '../helpers/chat'

test.describe('E2E-8 file upload @requires-auth', () => {
  test.beforeEach(() => {
    test.skip(!hasOperatorCredentials(), 'Set E2E_OPERATOR_A or E2E_EMAIL credentials')
  })

  test('upload file in chat and show attachment', async ({ page }) => {
    const fileName = `e2e-upload-${Date.now()}.txt`
    const uploadDir = join(tmpdir(), 'crm-e2e')
    mkdirSync(uploadDir, { recursive: true })
    const filePath = join(uploadDir, fileName)
    writeFileSync(filePath, `e2e attachment ${Date.now()}\n`, 'utf8')

    await loginAsOperatorA(page)
    await openFirstChat(page)

    const fileInput = page.locator('.message-input input[type="file"]')
    await fileInput.setInputFiles(filePath)
    await expect(page.locator('.message-input__file-tag', { hasText: fileName })).toBeVisible({
      timeout: 30_000,
    })

    await page.getByRole('button', { name: /^отправить$/i }).click()
    const attachment = page.locator('.message-list__attachments').last()
    await expect(attachment).toBeVisible({ timeout: 30_000 })
    await expect(attachment).toContainText(/e2e-upload|Файл #/i)

    const attachmentLink = page.locator('.message-list__attachments a').last()
    if (await attachmentLink.count()) {
      const [download] = await Promise.all([
        page.waitForEvent('download', { timeout: 15_000 }).catch(() => null),
        attachmentLink.click(),
      ])
      if (download) {
        expect(download.suggestedFilename().length).toBeGreaterThan(0)
      }
    }
  })
})
