import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TrialVpnDialog from '../src/widgets/chat/TrialVpnDialog.vue'

const mocks = vi.hoisted(() => ({ post: vi.fn(), send: vi.fn(), success: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ http: { post: mocks.post } }))
vi.mock('@/features/chats/api', () => ({ sendMessage: mocks.send }))
vi.mock('naive-ui', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    useMessage: () => ({ success: mocks.success }),
    NModal: defineComponent({ props: ['show'], setup: (props, { slots }) => () => props.show ? h('div', slots.default?.()) : null }),
    NButton: defineComponent({ props: ['disabled', 'loading'], setup: (props, { slots }) => () => h('button', { disabled: props.disabled }, slots.default?.()) }),
    NAlert: defineComponent({ setup: (_, { slots }) => () => h('div', slots.default?.()) }),
    NInputNumber: defineComponent({ props: ['value', 'disabled'], emits: ['update:value'], setup: (props, { emit }) => () => h('input', { value: props.value, disabled: props.disabled, type: 'number', onInput: (event: Event) => emit('update:value', Number((event.target as HTMLInputElement).value)) }) }),
  }
})

const subscription = { kind: 'trial', expires_at: 2000000000, happ_url: 'happ-example', clash_url: 'clash-example', v2rayng_url: 'v2ray-example', guide_url: 'guide-example' }
function dialog() {
  return mount(TrialVpnDialog, {
    props: { show: true, contactId: 12, botId: 5, chatId: 42 },
  })
}
async function click(wrapper: ReturnType<typeof dialog>, text: string) {
  const button = wrapper.findAll('button').find(item => item.text().includes(text))
  expect(button).toBeDefined()
  await button!.trigger('click'); await flushPromises()
}

describe('Chat trial VPN delivery', () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.post.mockReset(); mocks.send.mockReset() })
  it('selects a short trial, sends to the authorized chat and retries delivery without another subscription', async () => {
    mocks.post.mockResolvedValue({ data: subscription })
    mocks.send.mockRejectedValueOnce(new Error('delivery unavailable')).mockResolvedValueOnce({})
    const wrapper = dialog()
    await click(wrapper, '1 дн.')
    await click(wrapper, 'Выдать на 1 дн. и отправить')
    expect(mocks.post).toHaveBeenCalledWith('/vpn/subscriptions', expect.objectContaining({ contact_id: 12, source_chat_id: 42, source_bot_id: 5, kind: 'trial', days: 1 }))
    expect(wrapper.text()).toContain('Подписка создана, но сообщение не отправлено')
    await click(wrapper, 'Повторить отправку')
    expect(mocks.post).toHaveBeenCalledTimes(1)
    expect(mocks.send).toHaveBeenCalledTimes(2)
    expect(mocks.send.mock.calls[0]).toEqual(mocks.send.mock.calls[1])
    expect(mocks.send.mock.calls[1]?.[0]).toBe(42)
    expect(wrapper.emitted('update:show')?.[0]).toEqual([false])
    wrapper.unmount()
  })
  it('reuses the creation key after an uncertain API response', async () => {
    mocks.post.mockRejectedValueOnce(new Error('response lost')).mockResolvedValueOnce({ data: subscription })
    mocks.send.mockResolvedValue({})
    const wrapper = dialog()
    await click(wrapper, 'Выдать на 3 дн. и отправить')
    expect(mocks.send).not.toHaveBeenCalled()
    await click(wrapper, 'Выдать на 3 дн. и отправить')
    expect(mocks.post.mock.calls[0]).toEqual(mocks.post.mock.calls[1])
    expect(mocks.send).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
