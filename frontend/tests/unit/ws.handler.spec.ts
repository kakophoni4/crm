import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useChatsStore } from '@/features/chats/store'
import { routeChatTopicForTests } from '@/shared/realtime/chats-ws'
import { useAuthStore } from '@/shared/store/auth'

vi.mock('@/features/chats/api', () => ({
  listMessages: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
  listChats: vi.fn(),
}))

describe('chats WS handlers', () => {
  beforeEach(() => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().$patch({
      user: {
        id: 8,
        email: 'r@crm.local',
        full_name: 'Recipient',
        role: 'user',
        department_id: 1,
        group_id: null,
        presence: 'online',
        permissions: [],
      },
    })
  })

  it('handles inbound message and highlights chat', async () => {
    const store = useChatsStore()
    store.$patch({
      listItems: [
        {
          id: 5,
          contact_id: 1,
          contact_name: 'C',
          bot_id: null,
          assigned_user_id: 8,
          assigned_group_id: null,
          assigned_department_id: null,
          status: 'open',
          status_id: null,
          last_message_at: null,
          last_message_preview: null,
        },
      ],
    })

    await routeChatTopicForTests('chat.message.inbound', {
      chat_id: 5,
      message_id: 100,
    })

    expect(store.highlightedChatIds.has(5)).toBe(true)
    expect(store.listItems[0]?.unread_for_me).toBe(true)
  })

  it('ignores legacy chat transfer topic', () => {
    const store = useChatsStore()
    routeChatTopicForTests('chat.transfer.requested', {
      transfer_id: 1,
      chat_id: 2,
      from_user_id: 3,
      to_user_id: 8,
      requested_by: 3,
    })

    expect(store.currentChatId).toBe(null)
  })

  it('tracks takeover started and released', () => {
    const store = useChatsStore()
    routeChatTopicForTests('chat.takeover.started', {
      chat_id: 7,
      senior_user_id: 2,
      takeover_id: 11,
    })
    expect(store.takeoverByChatId[7]?.senior_user_id).toBe(2)

    routeChatTopicForTests('chat.takeover.released', { chat_id: 7 })
    expect(store.takeoverByChatId[7]).toBeUndefined()
  })
})
