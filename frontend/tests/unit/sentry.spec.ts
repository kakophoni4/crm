import { createApp } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ErrorEvent } from '@sentry/core'

import { router } from '@/app/router'
import { scrubSentryEvent } from '@/app/sentry'

describe('scrubSentryEvent', () => {
  it('redacts token query params from request url', () => {
    const event: ErrorEvent = {
      type: undefined,
      request: { url: '/login?redirect=/contacts&token=secret-jwt' },
    }
    scrubSentryEvent(event)
    expect(event.request?.url).toBe('/login?redirect=%2Fcontacts&token=%5BFiltered%5D')
  })

  it('removes user email from event payload', () => {
    const event: ErrorEvent = {
      type: undefined,
      user: { id: '42', email: 'agent@crm.local', username: 'agent@crm.local' },
    }
    scrubSentryEvent(event)
    expect(event.user).toEqual({ id: '42' })
  })
})

describe('initSentry', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('does not call Sentry.init without DSN', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', '')
    const Sentry = await import('@sentry/vue')
    const { initSentry: init } = await import('@/app/sentry')
    const app = createApp({ template: '<div />' })
    init(app, router)
    expect(Sentry.init).not.toHaveBeenCalled()
    vi.unstubAllEnvs()
  })

  it('calls Sentry.init when DSN is configured', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://example@o0.ingest.sentry.io/1')
    vi.stubEnv('VITE_SENTRY_ENVIRONMENT', 'test')
    const Sentry = await import('@sentry/vue')
    const { initSentry: init } = await import('@/app/sentry')
    const app = createApp({ template: '<div />' })
    init(app, router)
    expect(Sentry.init).toHaveBeenCalledWith(
      expect.objectContaining({
        dsn: 'https://example@o0.ingest.sentry.io/1',
        environment: 'test',
        sendDefaultPii: false,
      }),
    )
    vi.unstubAllEnvs()
  })
})

describe('app bootstrap', () => {
  it('imports main module without DSN', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', '')
    document.body.innerHTML = '<div id="app"></div>'
    await expect(import('@/main')).resolves.toBeDefined()
    vi.unstubAllEnvs()
  })
})
