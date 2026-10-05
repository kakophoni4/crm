import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import type { ChatDetail } from '../../src/entities/chat/types'
import ChatSidePane from '../../src/widgets/chat/ChatSidePane.vue'

const auth = vi.hoisted(() => ({ user: { permissions: ['contacts.read'] } }))
vi.mock('@/shared/store/auth', () => ({ useAuthStore: () => auth }))
vi.mock('@/features/chats/notifications-store', () => ({
  useChatNotificationsStore: () => ({ unreadCount: 0 }),
}))
vi.mock('naive-ui', async () => {
  const { defineComponent, h } = await import('vue')
  const slot = defineComponent({
    props: ['name', 'tab'],
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.()),
  })
  return { NTabs: slot, NTab: slot, NButton: slot, NEmpty: slot }
})
const chat = { id: 42, contact_id: 12, bot_id: 5 } as ChatDetail
function pane(modelValue: 'vpn' | 'payments' = 'vpn') {
  return shallowMount(ChatSidePane, {
    props: {
      modelValue,
      chat,
      bots: [],
      leadStatusOptions: [],
      wonStatusId: null,
      lostStatusId: null,
    },
    global: {
      stubs: {
        NTabs: { template: '<nav><slot /></nav>' },
        ContactVpnPanel: {
          name: 'ContactVpnPanel',
          props: ['contactId', 'chatId', 'botId'],
          template: '<div />',
        },
        ChatPaymentsSidePanel: {
          name: 'ChatPaymentsSidePanel',
          props: ['chat'],
          template: '<div />',
        },
      },
    },
  })
}
describe('shared chat side pane', () => {
  beforeEach(() => {
    auth.user.permissions = ['contacts.read']
  })
  it('passes the selected contact and chat to VPN and updates them when the chat changes', async () => {
    const wrapper = pane()
    expect(wrapper.findComponent({ name: 'ContactVpnPanel' }).props()).toMatchObject({
      contactId: 12,
      chatId: 42,
      botId: 5,
    })
    await wrapper.setProps({ chat: { ...chat, id: 43, contact_id: 13 } })
    expect(wrapper.findComponent({ name: 'ContactVpnPanel' }).props()).toMatchObject({
      contactId: 13,
      chatId: 43,
    })
    await wrapper.setProps({ modelValue: 'payments' })
    expect(wrapper.findComponent({ name: 'ContactVpnPanel' }).exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'ChatPaymentsSidePanel' }).props('chat').id).toBe(43)
    wrapper.unmount()
  })
  it('does not show a VPN tab or panel without contact access', () => {
    auth.user.permissions = []
    const wrapper = pane()
    expect(
      wrapper
        .findAllComponents({ name: 'NTab' })
        .some((tab) => tab.attributes('name') === 'vpn' || tab.props('name') === 'vpn'),
    ).toBe(false)
    expect(wrapper.findComponent({ name: 'ContactVpnPanel' }).exists()).toBe(false)
    wrapper.unmount()
  })
})
