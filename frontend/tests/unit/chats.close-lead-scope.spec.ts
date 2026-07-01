import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useChatsStore } from '@/features/chats/store'

const listMessagesMock = vi.fn()
const getChatMock = vi.fn()
const closeLeadMock = vi.fn()

vi.mock('@/features/chats/api', () => ({
  listChats: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
  getChat: (...args: unknown[]) => getChatMock(...args),
  listMessages: (...args: unknown[]) => listMessagesMock(...args),
  markChatRead: vi.fn().mockResolvedValue(undefined),
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
  closeLead: (...args: unknown[]) => closeLeadMock(...args),
  patchLead: vi.fn(),
  createContactLead: vi.fn(),
}))

vi.mock('@/shared/store/auth', () => ({
  useAuthStore: () => ({ user: { id: 1, role: 'user' } }),
}))

describe('close lead UX', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    listMessagesMock.mockReset()
    getChatMock.mockReset()
    closeLeadMock.mockReset()
    closeLeadMock.mockResolvedValue({ id: 42, closed_at: '2026-05-18T12:00:00Z' })
    getChatMock.mockResolvedValue({
      id: 1,
      contact_id: 10,
      assigned_group_id: 5,
      current_lead: { id: 42, status_id: 1, label: 'Новый', closed_at: null },
    })
    listMessagesMock.mockResolvedValue({ items: [{ id: 1 }], next_cursor: null })
  })

  it('reloads full chat after close', async () => {
    const store = useChatsStore()
    await store.openChat(1)
    await store.closeCurrentLead(99)
    expect(closeLeadMock).toHaveBeenCalledWith(42, 99)
    expect(listMessagesMock).toHaveBeenLastCalledWith(1, { limit: 50 })
  })
})
