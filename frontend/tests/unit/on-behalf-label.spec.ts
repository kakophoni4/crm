import { mount } from '@vue/test-utils'

import { NConfigProvider } from 'naive-ui'

import { describe, expect, it } from 'vitest'

import { defineComponent, h } from 'vue'



import { formatOnBehalfLabel } from '@/entities/contact/on-behalf-label'

import type { ChatMessage } from '@/entities/chat/types'

import MessageList from '@/widgets/chat/MessageList.vue'



describe('on_behalf label', () => {

  it('formats label per contract', () => {

    expect(

      formatOnBehalfLabel({

        is_on_behalf: true,

        author_full_name: 'Борис',

        card_owner_full_name: 'Аня',

      }),

    ).toBe('Ответил Борис (карточка: Аня)')

  })



  it('returns null when not on behalf', () => {

    expect(formatOnBehalfLabel({ is_on_behalf: false })).toBeNull()

  })



  it('renders tag in outbound message bubble', () => {

    const messages: ChatMessage[] = [

      {

        id: 1,

        chat_id: 10,

        direction: 'outbound',

        kind: 'text',

        text: 'Привет',

        attachments: [],

        sender_user_id: 2,

        reply_to_message_id: null,

        created_at: '2026-05-16T12:00:00Z',

        is_on_behalf: true,

        author_full_name: 'Борис',

        card_owner_full_name: 'Аня',

      },

    ]



    const Host = defineComponent({

      setup() {

        return () =>

          h(NConfigProvider, null, () => h(MessageList, { messages, loading: false }))

      },

    })



    const wrapper = mount(Host)

    expect(wrapper.text()).toContain('Ответил Борис (карточка: Аня)')

    wrapper.unmount()

  })

})


