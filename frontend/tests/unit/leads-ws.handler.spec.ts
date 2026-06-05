import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useChatsStore } from '@/features/chats/store'
import { routeLeadTopicForTests } from '@/shared/realtime/leads-ws'

const getChatMock = vi.fn()

vi.mock('@/features/chats/api', () => ({
  listChats: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
  getChat: (...args: unknown[]) => getChatMock(...args),
  listMessages: vi.fn(),
  sendMessage: vi.fn(),
  markChatRead: vi.fn(),
  patchChatStatusId: vi.fn(),
}))

describe('leads WS handlers', () => {
  beforeEach(() => {
    const pinia = createPinia()
    setActivePinia(pinia)
    getChatMock.mockReset()
    getChatMock.mockResolvedValue({
      id: 9,
      contact_id: 1,
      contact_name: 'Клиент',
      bot_id: null,
      assigned_user_id: null,
      assigned_group_id: 1,
      assigned_department_id: null,
      status: 'open',
      status_id: null,
      last_message_at: null,
      last_message_preview: null,
      current_lead: null,
    })
  })

  it('clears current lead on lead.closed', async () => {
    const store = useChatsStore()
    store.$patch({
      currentChatId: 9,
      currentChat: {
        id: 9,
        contact_id: 1,
        contact_name: 'Клиент',
        bot_id: null,
        assigned_user_id: null,
        assigned_group_id: 1,
        assigned_department_id: null,
        status: 'open',
        status_id: null,
        last_message_at: null,
        last_message_preview: null,
        current_lead: {
          id: 42,
          status_id: 3,
          label: 'Новый',
          closed_at: null,
        },
      },
    })

    await routeLeadTopicForTests('lead.closed', {
      lead_id: 42,
      chat_id: 9,
      closed_at: '2026-05-17T12:00:00Z',
    })

    expect(store.currentChat?.current_lead).toBeNull()
  })

  it('refreshes chat on lead.status_changed', async () => {
    const store = useChatsStore()
    getChatMock.mockResolvedValueOnce({
      id: 9,
      contact_id: 1,
      contact_name: 'Клиент',
      bot_id: null,
      assigned_user_id: null,
      assigned_group_id: 1,
      assigned_department_id: null,
      status: 'open',
      status_id: null,
      last_message_at: null,
      last_message_preview: null,
      current_lead: {
        id: 42,
        status_id: 4,
        label: 'В работе',
        closed_at: null,
      },
    })
    store.$patch({
      currentChatId: 9,
      currentChat: {
        id: 9,
        contact_id: 1,
        contact_name: 'Клиент',
        bot_id: null,
        assigned_user_id: null,
        assigned_group_id: 1,
        assigned_department_id: null,
        status: 'open',
        status_id: null,
        last_message_at: null,
        last_message_preview: null,
        current_lead: {
          id: 42,
          status_id: 3,
          label: 'Новый',
          closed_at: null,
        },
      },
    })

    await routeLeadTopicForTests('lead.status_changed', {
      lead_id: 42,
      chat_id: 9,
      to_status_id: 4,
    })

    expect(getChatMock).toHaveBeenCalledWith(9)
    expect(store.currentChat?.current_lead?.label).toBe('В работе')
  })
})
