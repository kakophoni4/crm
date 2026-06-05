import MockAdapter from 'axios-mock-adapter'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { http } from '@/shared/api/http'
import { storage } from '@/shared/lib/storage'
import { setupAuthHttpInterceptors, useAuthStore } from '@/shared/store/auth'

vi.mock('@/shared/realtime/contacts-ws', () => ({
  connectContactsRealtime: vi.fn(),
  disconnectContactsRealtime: vi.fn(),
}))

const ACCESS_KEY = 'crm.auth.access_token'
const REFRESH_KEY = 'crm.auth.refresh_token'

describe('auth store', () => {
  let mock: MockAdapter

  beforeEach(() => {
    setActivePinia(createPinia())
    setupAuthHttpInterceptors()
    mock = new MockAdapter(http)
    storage.remove(ACCESS_KEY)
    storage.remove(REFRESH_KEY)
  })

  afterEach(() => {
    mock.restore()
  })

  it('logs in and persists tokens', async () => {
    mock.onPost('/auth/login').reply(200, {
      access_token: 'access-1',
      refresh_token: 'refresh-1',
      token_type: 'Bearer',
      expires_in: 900,
      user: { id: 1, email: 'admin@crm.local', full_name: 'Admin', role: 'admin' },
    })
    mock.onGet('/auth/me').reply(200, {
      id: 1,
      email: 'admin@crm.local',
      full_name: 'Admin',
      role: 'admin',
      department_id: null,
      group_id: null,
      presence: 'online',
      permissions: ['contacts.read'],
    })

    const auth = useAuthStore()
    await auth.login('admin@crm.local', 'secret')

    expect(auth.isAuthenticated).toBe(true)
    expect(auth.user?.role).toBe('admin')
    expect(storage.get(ACCESS_KEY)).toBe('access-1')
    expect(storage.get(REFRESH_KEY)).toBe('refresh-1')
  })

  it('refreshes on 401 and retries request', async () => {
    const auth = useAuthStore()
    auth.$patch({
      accessToken: 'expired',
      refreshToken: 'refresh-1',
    })

    mock.onPost('/auth/refresh').reply(200, {
      access_token: 'access-2',
      refresh_token: 'refresh-2',
      token_type: 'Bearer',
      expires_in: 900,
    })

    let contactsCalls = 0
    mock.onGet('/contacts').reply((config) => {
      contactsCalls += 1
      const authHeader = config.headers?.Authorization as string | undefined
      if (contactsCalls === 1) {
        expect(authHeader).toBe('Bearer expired')
        return [401, { error: { code: 'unauthorized', message: 'expired' } }]
      }
      expect(authHeader).toBe('Bearer access-2')
      return [200, { items: [], next_cursor: null }]
    })

    const { listContacts } = await import('@/features/contacts/api')
    const data = await listContacts({ limit: 10 })

    expect(data.items).toEqual([])
    expect(auth.accessToken).toBe('access-2')
    expect(contactsCalls).toBe(2)
  })

  it('clears session when refresh fails', async () => {
    const auth = useAuthStore()
    auth.$patch({
      accessToken: 'expired',
      refreshToken: 'bad-refresh',
    })

    mock.onPost('/auth/refresh').reply(401, {
      error: { code: 'unauthorized', message: 'invalid refresh' },
    })
    mock.onGet('/contacts').reply(401, {
      error: { code: 'unauthorized', message: 'expired' },
    })

    const { listContacts } = await import('@/features/contacts/api')
    await expect(listContacts({ limit: 10 })).rejects.toMatchObject({ code: 'unauthorized' })
    expect(auth.isAuthenticated).toBe(false)
  })
})
