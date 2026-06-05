import { flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'

import MessageInput from '@/widgets/chat/MessageInput.vue'

const uploadFileMock = vi.fn()

vi.mock('@/features/chats/api', () => ({
  uploadFile: (...args: unknown[]) => uploadFileMock(...args),
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

describe('MessageInput drag-and-drop', () => {
  it('queues attachment after file drop', async () => {
    uploadFileMock.mockResolvedValue({ id: 42 })
    const wrapper = mountInput()
    const input = wrapper.findComponent(MessageInput)
    const file = new File(['hello'], 'contract.pdf', { type: 'application/pdf' })
    const dataTransfer = {
      files: [file],
    }

    await input.find('.message-input').trigger('drop', {
      dataTransfer,
    })
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledWith(file)
    expect(input.text()).toContain('contract.pdf')
    wrapper.unmount()
    document.body.innerHTML = ''
  })
})
