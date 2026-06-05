import { ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider, NNotificationProvider } from 'naive-ui'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import type { ChatListItem } from '@/entities/chat/types'
import ChatsPage from '@/pages/chats/index.vue'
import { useAuthStore } from '@/shared/store/auth'

const sampleChats: ChatListItem[] = [
  {
    id: 101,
    contact_id: 7,
    contact_name: 'Иван Петров',
    bot_id: 2,
    assigned_user_id: 5,
    assigned_group_id: 1,
    assigned_department_id: 1,
    status: 'in_progress',
    status_id: 2,
    last_message_at: '2026-05-16T10:00:00Z',
    last_message_preview: 'Здравствуйте',
    unread_for_me: true,
    card_owner_user_id: 5,
  },
]

const listChatsMock = vi.fn()
const listBotsMock = vi.fn()
const listContactTransfersMock = vi.fn()

vi.mock('@/features/chats/api', () => ({
  listChats: (...args: unknown[]) => listChatsMock(...args),
  getChat: vi.fn(),
  listMessages: vi.fn(),
  sendMessage: vi.fn(),
  uploadFile: vi.fn(),
  markChatRead: vi.fn().mockResolvedValue(undefined),
}))

vi.mock('@/shared/realtime/ws-client', () => ({
  connectRealtime: vi.fn(),
  getRealtimeWS: () => ({ onTopic: () => () => {} }),
}))

vi.mock('@/features/bots/api', () => ({
  listBots: (...args: unknown[]) => listBotsMock(...args),
}))

vi.mock('@/shared/realtime/chats-ws', () => ({
  connectChatsRealtime: vi.fn(),
}))

vi.mock('@/shared/realtime/leads-ws', () => ({
  connectLeadsRealtime: vi.fn(),
}))

vi.mock('@/shared/realtime/ownership-ws', () => ({
  connectOwnershipRealtime: vi.fn(),
}))

vi.mock('@/features/leads/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/leads/api')>()
  return {
    ...actual,
    listStatuses: vi.fn().mockResolvedValue({ items: [] }),
  }
})

vi.mock('@/shared/lib/query-invalidation', () => ({
  onChatsInvalidate: () => () => undefined,
}))

vi.mock('@vueuse/core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@vueuse/core')>()
  return {
    ...actual,
    useWindowSize: () => ({ width: ref(1280), height: ref(800) }),
  }
})

vi.mock('@/features/contacts/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/contacts/api')>()
  return {
    ...actual,
    listContactTransfers: (...args: unknown[]) => listContactTransfersMock(...args),
  }
})

function mountChatsPage() {
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

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/chats', name: 'chats', component: ChatsPage }],
  })

  const Host = defineComponent({
    setup() {
      return () =>
        h(NConfigProvider, null, () =>
          h(NNotificationProvider, null, () =>
            h(NMessageProvider, null, () => h(ChatsPage)),
          ),
        )
    },
  })

  return mount(Host, { global: { plugins: [pinia, router] } })
}

describe('chats list page', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    listChatsMock.mockReset()
    listChatsMock.mockResolvedValue({ items: sampleChats, next_cursor: null })
    listBotsMock.mockReset()
    listBotsMock.mockResolvedValue({
      items: [{ id: 2, code: 'bot_a', name: 'Support', purpose: null, owner_type: 'group', owner_id: 1, is_active: true, last_seen_at: null }],
    })
    listContactTransfersMock.mockReset()
    listContactTransfersMock.mockResolvedValue({ items: [] })
  })

  afterEach(async () => {
    await vi.runOnlyPendingTimersAsync()
    vi.useRealTimers()
  })

  it('renders chat rows from API', async () => {
    const wrapper = mountChatsPage()
    await flushPromises()

    expect(listChatsMock).toHaveBeenCalled()
    expect(wrapper.text()).toContain('Иван Петров')
    expect(wrapper.text()).toContain('Здравствуйте')
    wrapper.unmount()
  })

  it('shows unread dot when unread_for_me is true', async () => {
    const wrapper = mountChatsPage()
    await flushPromises()

    expect(wrapper.find('.n-badge').exists()).toBe(true)
    wrapper.unmount()
  })

  it('debounces search and sends q to API', async () => {
    const wrapper = mountChatsPage()
    await flushPromises()
    listChatsMock.mockClear()

    const store = (
      await import('@/features/chats/store')
    ).useChatsStore()
    store.filters.q = 'Иван'
    await vi.advanceTimersByTimeAsync(300)
    await flushPromises()

    expect(listChatsMock).toHaveBeenCalledWith(expect.objectContaining({ q: 'Иван' }))
    wrapper.unmount()
  })

  it('shows empty filters message when list is empty', async () => {
    listChatsMock.mockResolvedValue({ items: [], next_cursor: null })
    const wrapper = mountChatsPage()
    await flushPromises()

    expect(wrapper.text()).toContain('Нет чатов по фильтрам')
    wrapper.unmount()
  })
})
