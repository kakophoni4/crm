import { createPinia, setActivePinia } from 'pinia'

import { beforeEach, describe, expect, it, vi } from 'vitest'



import { useChatsStore } from '@/features/chats/store'

import { routeOwnershipTopicForTests } from '@/shared/realtime/ownership-ws'

import { useAuthStore } from '@/shared/store/auth'



vi.mock('@/features/chats/api', () => ({

  listChats: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),

  listMessages: vi.fn(),

}))



describe('ownership WS handlers', () => {

  beforeEach(() => {

    const pinia = createPinia()

    setActivePinia(pinia)

    useAuthStore().$patch({

      user: {

        id: 5,

        email: 'u@crm.local',

        full_name: 'Operator',

        role: 'user',

        department_id: 1,

        group_id: 1,

        presence: 'online',

        permissions: [],

      },

    })

  })



  it('marks chat as needs response on group escalation', () => {

    const store = useChatsStore()

    store.$patch({

      listItems: [

        {

          id: 12,

          contact_id: 3,

          contact_name: 'Клиент',

          bot_id: 1,

          assigned_user_id: 5,

          assigned_group_id: 1,

          assigned_department_id: 1,

          status: 'open',

          status_id: null,

          last_message_at: null,

          last_message_preview: null,


        },

      ],

    })



    routeOwnershipTopicForTests('contact.escalation.group_notify', {

      contact_id: 3,

      group_id: 1,

      chat_id: 12,

    })



    expect(store.needsResponseChatIds.has(12)).toBe(true)

    expect(store.highlightedChatIds.has(12)).toBe(true)

  })



  it('updates ownership on reassigned event', () => {

    const store = useChatsStore()

    store.$patch({

      listItems: [

        {

          id: 20,

          contact_id: 9,

          contact_name: 'Марина',

          bot_id: 1,

          assigned_user_id: 5,

          assigned_group_id: 2,

          assigned_department_id: 1,

          status: 'open',

          status_id: null,

          last_message_at: null,

          last_message_preview: null,


        },

      ],

    })



    routeOwnershipTopicForTests('contact.ownership.reassigned', {

      contact_id: 9,

      group_id: 2,

      to_user_id: 8,

    })



    expect(store.listItems[0]?.card_owner_user_id).toBe(8)

  })



  it('patches message on behalf from WS', () => {

    const store = useChatsStore()

    store.$patch({

      currentChatId: 4,

      messages: [

        {

          id: 100,

          chat_id: 4,

          direction: 'outbound',

          kind: 'text',

          text: 'ok',

          attachments: [],

          sender_user_id: 8,

          reply_to_message_id: null,

          created_at: '2026-05-16T12:00:00Z',

        },

      ],

    })



    routeOwnershipTopicForTests('message.replied.on_behalf', {

      chat_id: 4,

      message_id: 100,

      author_user_id: 8,

      card_owner_user_id: 5,

    })



    expect(store.messages[0]?.is_on_behalf).toBe(true)

    expect(store.messages[0]?.card_owner_user_id).toBe(5)

  })

})


