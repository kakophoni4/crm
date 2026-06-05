import { vi } from 'vitest'

vi.mock('@sentry/vue', () => ({
  init: vi.fn(),
  browserTracingIntegration: vi.fn(() => ({})),
  captureException: vi.fn(),
  setUser: vi.fn(),
}))
