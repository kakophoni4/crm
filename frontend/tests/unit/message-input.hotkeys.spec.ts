import { flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'

import MessageInput from '@/widgets/chat/MessageInput.vue'

vi.mock('@/features/chats/api', () => ({
  uploadFile: vi.fn(),
}))

function mountInput() {
  const Host = defineComponent({
    setup() {
      return () =>
        h(NConfigProvider, null, () =>
          h(NMessageProvider, null, () => h(MessageInput)),
        )
    },
  })
  return mount(Host, { attachTo: document.body })
}

describe('MessageInput send hotkeys', () => {
  it('emits send on Enter', async () => {
    const wrapper = mountInput()
    const input = wrapper.findComponent(MessageInput)
    const textarea = wrapper.find('textarea')

    await textarea.setValue('Привет')
    await textarea.trigger('keydown', { key: 'Enter' })
    await flushPromises()

    expect(input.emitted('send')?.[0]).toEqual(['Привет', [], null])
    wrapper.unmount()
    document.body.innerHTML = ''
  })

  it('does not emit send on Shift+Enter', async () => {
    const wrapper = mountInput()
    const input = wrapper.findComponent(MessageInput)
    const textarea = wrapper.find('textarea')

    await textarea.setValue('Line break')
    await textarea.trigger('keydown', { key: 'Enter', shiftKey: true })
    await flushPromises()

    expect(input.emitted('send')).toBeUndefined()
    wrapper.unmount()
    document.body.innerHTML = ''
  })

  it('does not emit send on Ctrl+Enter', async () => {
    const wrapper = mountInput()
    const input = wrapper.findComponent(MessageInput)
    const textarea = wrapper.find('textarea')

    await textarea.setValue('Hello')
    await textarea.trigger('keydown', { key: 'Enter', ctrlKey: true })
    await flushPromises()

    expect(input.emitted('send')).toBeUndefined()
    wrapper.unmount()
    document.body.innerHTML = ''
  })
})
