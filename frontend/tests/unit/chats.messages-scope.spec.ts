import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useChatsStore } from '@/features/chats/store'

const listMessagesMock = vi.fn()
const getChatMock = vi.fn()
const markChatReadMock = vi.fn()

vi.mock('@/features/chats/api', () => ({
  listChats: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
  getChat: (...args: unknown[]) => getChatMock(...args),
  listMessages: (...args: unknown[]) => listMessagesMock(...args),
  markChatRead: (...args: unknown[]) => markChatReadMock(...args) ?? Promise.resolve(),
  patchChatStatusId: vi.fn(),
  sendMessage: vi.fn(),
}))

vi.mock('@/features/chats/ownership-enrich', () => ({
  applyOwnershipToChat: (c: unknown) => c,
  enrichMessagesWithReplyAudit: async (_cid: number, _gid: number | null, items: unknown[]) =>
    items,
  ownershipKey: () => 'k',
}))

vi.mock('@/features/leads/api', () => ({
  closeLead: vi.fn(),
  patchLead: vi.fn(),
}))

vi.mock('@/shared/store/auth', () => ({
  useAuthStore: () => ({ user: { id: 1, role: 'user' } }),
}))

describe('chats message scope', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    listMessagesMock.mockReset()
    getChatMock.mockReset()
    markChatReadMock.mockReset()
    markChatReadMock.mockResolvedValue(undefined)
    getChatMock.mockResolvedValue({
      id: 1,
      contact_id: 10,
      assigned_group_id: 5,
      current_lead: { id: 42, status_id: 1, label: 'Новый', closed_at: null },
    })
    listMessagesMock.mockResolvedValue({ items: [{ id: 1, lead_id: 42 }], next_cursor: null })
  })

  it('loads all chat messages by default', async () => {
    const store = useChatsStore()
    await store.openChat(1)
    expect(listMessagesMock).toHaveBeenCalledWith(1, { limit: 50, lead_id: undefined })
  })

  it('switches to current lead with lead_id param', async () => {
    const store = useChatsStore()
    await store.openChat(1)
    listMessagesMock.mockClear()
    listMessagesMock.mockResolvedValue({ items: [{ id: 1, lead_id: 42 }], next_cursor: null })
    await store.setMessageScope('current_lead')
    expect(listMessagesMock).toHaveBeenCalledWith(1, { limit: 50, lead_id: 42 })
  })

  it('switches to all chat without lead_id', async () => {
    const store = useChatsStore()
    await store.openChat(1)
    listMessagesMock.mockClear()
    listMessagesMock.mockResolvedValue({ items: [{ id: 1 }, { id: 2 }], next_cursor: null })
    await store.setMessageScope('all')
    expect(listMessagesMock).toHaveBeenCalledWith(1, { limit: 50, lead_id: undefined })
    expect(store.messages).toHaveLength(2)
  })
})
