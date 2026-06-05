import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChatMessage } from '@/entities/chat/types'
import { useChatsStore } from '@/features/chats/store'
import { useAuthStore } from '@/shared/store/auth'

const sendMessageMock = vi.fn()

vi.mock('@/features/chats/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/chats/api')>()
  return {
    ...actual,
    sendMessage: (...args: unknown[]) => sendMessageMock(...args),
  }
})

describe('chats send optimistic update', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().$patch({
      accessToken: 't',
      user: {
        id: 5,
        email: 'u@crm.local',
        full_name: 'Op',
        role: 'user',
        department_id: 1,
        group_id: null,
        presence: 'online',
        permissions: [],
      },
    })
  })

  it('adds optimistic message then replaces with server row', async () => {
    const store = useChatsStore()
    store.$patch({
      currentChatId: 10,
      listItems: [
        {
          id: 10,
          contact_id: 1,
          contact_name: 'Test',
          bot_id: null,
          assigned_user_id: 5,
          assigned_group_id: null,
          assigned_department_id: null,
          status: 'open',
          status_id: null,
          last_message_at: null,
          last_message_preview: null,
        },
      ],
    })

    const saved: ChatMessage = {
      id: 99,
      chat_id: 10,
      direction: 'outbound',
      kind: 'text',
      text: 'Привет',
      attachments: [],
      sender_user_id: 5,
      reply_to_message_id: null,
      created_at: '2026-05-16T12:00:00Z',
      idempotency_key: 'key-1',
    }

    sendMessageMock.mockResolvedValue(saved)

    await store.sendMessage('Привет')

    expect(sendMessageMock).toHaveBeenCalledWith(
      10,
      expect.objectContaining({ text: 'Привет', idempotency_key: expect.any(String) }),
    )
    expect(store.messages.some((m) => m._optimistic)).toBe(false)
    expect(store.messages.some((m) => m.id === 99)).toBe(true)
  })

  it('marks optimistic row failed on API error', async () => {
    const store = useChatsStore()
    store.$patch({ currentChatId: 10 })
    sendMessageMock.mockRejectedValue(new Error('takeover active'))

    await expect(store.sendMessage('fail')).rejects.toThrow()
    expect(store.messages.some((m) => m._failed)).toBe(true)
  })
})
