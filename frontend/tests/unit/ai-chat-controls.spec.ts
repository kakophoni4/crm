import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AIChatControls from '../../src/widgets/chat/AIChatControls.vue'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ http: api }))
vi.mock('naive-ui', async () => {
  const { defineComponent, h } = await import('vue')
  const slot = defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('div', [slots.trigger?.(), slots.default?.()]),
  })
  return {
    NTag: slot,
    NModal: defineComponent({ props: ['show'], setup: (props, { slots }) => () => props.show ? h('div', slots.default?.()) : null }),
    NCheckbox: slot,
    NButton: defineComponent({
      props: ['disabled'],
      setup:
        (props, { slots }) =>
        () =>
          h('button', { disabled: props.disabled }, slots.default?.()),
    }),
  }
})
const state = (mode: string) => ({ data: { mode, global_enabled: true, data: {} } })
describe('chat AI controls', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })
  afterEach(() => vi.useRealTimers())


  it('hides the status bar while AI is off but exposes the settings on demand', async () => {
    api.get.mockResolvedValue(state('OFF'))
    const wrapper = mount(AIChatControls, { props: { chatId: 10 } })
    await flushPromises()
    expect(wrapper.find('.ai-controls').exists()).toBe(false)
    expect(wrapper.text()).toBe('')
    wrapper.vm.open(); await flushPromises()
    expect(wrapper.text()).toContain('Включить ИИ')
    wrapper.unmount()
  })

  it('does not apply a previous chat mutation to the newly opened chat', async () => {
    api.get.mockResolvedValueOnce(state('MANAGER')).mockResolvedValueOnce(state('OFF'))
    let finish!: (value: ReturnType<typeof state>) => void
    api.put.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    const wrapper = mount(AIChatControls, { props: { chatId: 10 } })
    await flushPromises()
    wrapper.vm.open()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((button) => button.text() === 'Включить ИИ')!
      .trigger('click')
    expect(api.put).toHaveBeenCalledWith('/ai/chats/10', {
      mode: 'ASSISTANT',
      fallback_enabled: false,
    })
    await wrapper.setProps({ chatId: 20 })
    await flushPromises()
    finish(state('ASSISTANT'))
    await flushPromises()
    expect(wrapper.text()).not.toContain('ИИ выключен')
    expect(wrapper.text()).not.toContain('Отвечает ИИ')
    expect(
      wrapper.findAll('button').some((button) => button.attributes('disabled') !== undefined),
    ).toBe(false)
    wrapper.unmount()
  })

  it('keeps the current chat controls visible when a previous chat request fails', async () => {
    let fail!: (reason: Error) => void
    api.get
      .mockReturnValueOnce(
        new Promise((_, reject) => {
          fail = reject
        }),
      )
      .mockResolvedValueOnce(state('MANAGER'))
    const wrapper = mount(AIChatControls, { props: { chatId: 10 } })
    await wrapper.setProps({ chatId: 20 })
    await flushPromises()
    fail(new Error('Old request failed'))
    await flushPromises()
    wrapper.vm.open()
    await flushPromises()
    expect(wrapper.text()).toContain('Работает менеджер')
    wrapper.unmount()
  })
})
