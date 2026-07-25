import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ChatMessage } from '@/entities/chat/types'
import { getChatSnapshot, setChatSnapshot } from '@/features/chats/snapshot-cache'
import { useChatsStore } from '@/features/chats/store'
import { useAuthStore } from '@/shared/store/auth'

const sendMessageMock = vi.fn()
const listMessagesMock = vi.fn()
const getChatMock = vi.fn()
const markChatReadMock = vi.fn()

vi.mock('@/features/chats/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/chats/api')>()
  return {
    ...actual,
    sendMessage: (...args: unknown[]) => sendMessageMock(...args),
    listMessages: (...args: unknown[]) => listMessagesMock(...args),
    getChat: (...args: unknown[]) => getChatMock(...args),
    markChatRead: (...args: unknown[]) => markChatReadMock(...args) ?? Promise.resolve(),
  }
})

vi.mock('@/features/chats/ownership-enrich', () => ({
  applyOwnershipToChat: (c: unknown) => c,
  enrichMessagesWithReplyAudit: async (_cid: number, _gid: number | null, items: unknown[]) =>
    items,
  ownershipKey: () => 'k',
}))

function baseListItem(id: number) {
  return {
    id,
    contact_id: id,
    contact_name: `Chat ${id}`,
    bot_id: null,
    assigned_user_id: 5,
    assigned_group_id: null,
    assigned_department_id: null,
    status: 'open' as const,
    status_id: null,
    last_message_at: null,
    last_message_preview: null,
  }
}

describe('chats send race across chat switch', () => {
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
    markChatReadMock.mockResolvedValue(undefined)
  })

  it('does not append POST result into a newly opened chat', async () => {
    const store = useChatsStore()
    store.$patch({
      currentChatId: 10,
      currentChat: { ...baseListItem(10) } as never,
      listItems: [baseListItem(10), baseListItem(20)],
      messages: [],
    })
    setChatSnapshot(10, {
      detail: { ...baseListItem(10) } as never,
      messages: [],
      nextCursor: null,
    })

    let resolveSend!: (value: ChatMessage) => void
    sendMessageMock.mockImplementation(
      () =>
        new Promise<ChatMessage>((resolve) => {
          resolveSend = resolve
        }),
    )

    const sendPromise = store.sendMessage('Привет')
    expect(store.messages.some((m) => m._optimistic && m.chat_id === 10)).toBe(true)

    getChatMock.mockResolvedValue({ ...baseListItem(20), current_lead: null })
    listMessagesMock.mockResolvedValue({ items: [], next_cursor: null })
    await store.openChat(20)

    expect(store.currentChatId).toBe(20)
    expect(store.messages.every((m) => m.chat_id !== 10 || m.id > 0)).toBe(true)

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
      idempotency_key: 'key-race',
    }
    resolveSend(saved)
    await sendPromise

    expect(store.currentChatId).toBe(20)
    expect(store.messages.some((m) => m.id === 99)).toBe(false)
    const snap = getChatSnapshot(10)
    expect(snap?.messages.some((m) => m.id === 99)).toBe(true)
  })
})
