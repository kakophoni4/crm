import * as Sentry from '@sentry/vue'
import type { ErrorEvent, EventHint } from '@sentry/core'
import type { App } from 'vue'
import type { Router } from 'vue-router'

const PII_QUERY_KEYS = new Set([
  'token',
  'access_token',
  'refresh_token',
  'password',
  'secret',
  'authorization',
  'code',
  'signature',
])

const PII_DATA_KEYS = new Set([
  ...PII_QUERY_KEYS,
  'email',
  'password',
  'authorization',
  'access_token',
  'refresh_token',
])

function scrubQueryInUrl(raw: string): string {
  try {
    const base = typeof window !== 'undefined' ? window.location.origin : 'http://localhost'
    const url = new URL(raw, base)
    for (const key of [...url.searchParams.keys()]) {
      if (PII_QUERY_KEYS.has(key.toLowerCase())) {
        url.searchParams.set(key, '[Filtered]')
      }
    }
    if (raw.startsWith('http://') || raw.startsWith('https://')) {
      return url.toString()
    }
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return raw
  }
}

function scrubMapping(data: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(data)) {
    if (PII_DATA_KEYS.has(key.toLowerCase())) {
      out[key] = '[Filtered]'
      continue
    }
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      out[key] = scrubMapping(value as Record<string, unknown>)
    } else if (Array.isArray(value)) {
      out[key] = value.map((item) =>
        item && typeof item === 'object' && !Array.isArray(item)
          ? scrubMapping(item as Record<string, unknown>)
          : item,
      )
    } else {
      out[key] = value
    }
  }
  return out
}

/** Scrub PII from a Sentry event (exported for unit tests). */
export function scrubSentryEvent(event: ErrorEvent): ErrorEvent {
  const request = event.request
  if (request && typeof request.url === 'string') {
    request.url = scrubQueryInUrl(request.url)
  }

  const breadcrumbs = event.breadcrumbs
  if (Array.isArray(breadcrumbs)) {
    for (const crumb of breadcrumbs) {
      const data = crumb.data
      if (!data || typeof data !== 'object') continue
      if (typeof data.url === 'string') {
        data.url = scrubQueryInUrl(data.url)
      }
      if (typeof data.from === 'string') {
        data.from = scrubQueryInUrl(data.from)
      }
      if (typeof data.to === 'string') {
        data.to = scrubQueryInUrl(data.to)
      }
    }
  }

  const extra = event.extra
  if (extra && typeof extra === 'object') {
    event.extra = scrubMapping(extra as Record<string, unknown>)
  }

  const user = event.user
  if (user && typeof user === 'object') {
    const { email: _email, username, ...rest } = user as Record<string, unknown>
    if (typeof username === 'string' && username.includes('@')) {
      event.user = rest
    } else if (_email !== undefined) {
      event.user = rest
    }
  }

  return event
}

function beforeSend(event: ErrorEvent, hint: EventHint): ErrorEvent | null {
  void hint
  return scrubSentryEvent(event)
}

function sentryEnvironment(): string {
  return import.meta.env.VITE_SENTRY_ENVIRONMENT?.trim() || import.meta.env.MODE
}

/** Init Sentry when `VITE_SENTRY_DSN` is set. Call before `app.mount()`. */
export function initSentry(app: App, router: Router): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN?.trim()
  if (!dsn) return

  Sentry.init({
    app,
    dsn,
    environment: sentryEnvironment(),
    sendDefaultPii: false,
    beforeSend,
    integrations: [Sentry.browserTracingIntegration({ router })],
    tracesSampleRate: 0,
  })
}

/** Set Sentry user context without email (optional, call after auth). */
export function setSentryUser(user: { id: number } | null): void {
  if (!import.meta.env.VITE_SENTRY_DSN?.trim()) return
  if (!user) {
    Sentry.setUser(null)
    return
  }
  Sentry.setUser({ id: String(user.id) })
}
