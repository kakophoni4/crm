import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import MessageAttachment from '@/widgets/chat/MessageAttachment.vue'

vi.mock('@vueuse/core', () => ({
  useIntersectionObserver: (_target: unknown, callback: (entries: Array<{ isIntersecting: boolean }>) => void) => {
    void Promise.resolve().then(() => callback([{ isIntersecting: true }]))
    return { stop: vi.fn() }
  },
}))

vi.mock('@/shared/lib/attachment-blob-cache', () => ({
  peekAttachmentBlobUrl: vi.fn(() => null),
  fetchAttachmentBlobUrl: vi.fn(() => Promise.resolve('blob:test-image')),
}))

describe('MessageAttachment image preview', () => {
  it('opens and closes image preview inside the app', async () => {
    const wrapper = mount(MessageAttachment, {
      props: {
        att: {
          type: 'photo',
          status: 'ready',
          download_path: '/api/v1/files/1',
          filename: 'screen.png',
          mime: 'image/png',
        },
      },
      attachTo: document.body,
    })

    await nextTick()
    await flushPromises()
    await nextTick()

    await wrapper.find('.message-attachment__image').trigger('click')
    const preview = document.body.querySelector('.attachment-preview')
    expect(preview).not.toBeNull()

    document.body
      .querySelector('.attachment-preview__stage')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()
    expect(document.body.querySelector('.attachment-preview')).toBeNull()

    wrapper.unmount()
  })
})
