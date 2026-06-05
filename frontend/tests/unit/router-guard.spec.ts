import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { requireAuth } from '@/app/router'
import { useAuthStore } from '@/shared/store/auth'

describe('requireAuth', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('returns false without access token', () => {
    expect(requireAuth()).toBe(false)
  })

  it('returns true when access token is set', () => {
    const auth = useAuthStore()
    auth.$patch({ accessToken: 'test-token' })
    expect(requireAuth()).toBe(true)
  })
})
