import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useChatsStore } from '@/features/chats/store'
import { useAuthStore } from '@/shared/store/auth'

const listChatsMock = vi.fn()

vi.mock('@/features/chats/api', () => ({
  listChats: (...args: unknown[]) => listChatsMock(...args),
  getChat: vi.fn(),
  listMessages: vi.fn(),
  sendMessage: vi.fn(),
  uploadFile: vi.fn(),
  markChatRead: vi.fn(),
}))

function setupStore() {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().$patch({
    accessToken: 'token',
    user: {
      id: 5,
      email: 'u@crm.local',
      full_name: 'Operator',
      role: 'user',
      department_id: 1,
      group_id: 1,
      presence: 'online',
      permissions: ['chats.read'],
    },
  })
  return useChatsStore()
}

describe('chats store list filters', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    listChatsMock.mockReset()
    listChatsMock.mockResolvedValue({ items: [], next_cursor: null })
  })

  afterEach(async () => {
    await vi.runOnlyPendingTimersAsync()
    vi.useRealTimers()
  })

  it('passes card_owner_user_id on mine tab', async () => {
    const store = setupStore()
    store.listTab = 'mine'
    await store.fetchList()
    expect(listChatsMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ card_owner_user_id: 5 }),
    )
  })

  it('passes needs_reply on needs_response tab', async () => {
    const store = setupStore()
    store.listTab = 'needs_response'
    await store.fetchList()
    expect(listChatsMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ needs_reply: true }),
    )
  })

  it('omits card_owner_user_id on group tab', async () => {
    const store = setupStore()
    store.listTab = 'group'
    await store.fetchList()
    const params = listChatsMock.mock.calls.at(-1)?.[0] as Record<string, unknown>
    expect(params.card_owner_user_id).toBeUndefined()
  })

  it('passes lead filters when set', async () => {
    const store = setupStore()
    store.filters.leadStatusId = 12
    store.filters.leadOpenOnly = true
    await store.fetchList()
    expect(listChatsMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        lead_status_id: 12,
        lead_open_only: true,
      }),
    )
  })

  it('passes bot_id, unread_only and sort from filters', async () => {
    const store = setupStore()
    store.filters.botId = 2
    store.filters.unreadOnly = true
    store.filters.sort = 'unread_first'
    await store.fetchList()
    expect(listChatsMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        bot_id: 2,
        unread_only: true,
        sort: 'unread_first',
      }),
    )
  })

  it('debounces search q before refetch', async () => {
    const store = setupStore()
    listChatsMock.mockClear()
    store.filters.q = 'Иван'
    await vi.advanceTimersByTimeAsync(299)
    expect(listChatsMock).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    await vi.runAllTimersAsync()
    expect(listChatsMock).toHaveBeenCalledWith(expect.objectContaining({ q: 'Иван' }))
  })
})
