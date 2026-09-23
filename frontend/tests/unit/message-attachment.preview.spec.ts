import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import MessageAttachment from '@/widgets/chat/MessageAttachment.vue'

vi.mock('@vueuse/core', async (importOriginal) => ({
  ...await importOriginal<typeof import('@vueuse/core')>(),
  useIntersectionObserver: (_target: unknown, callback: (entries: Array<{ isIntersecting: boolean }>) => void) => {
    void Promise.resolve().then(() => callback([{ isIntersecting: true }]))
    return { stop: vi.fn() }
  },
}))

const { fetchAttachmentBlob, peekAttachmentBlob } = vi.hoisted(() => ({
  fetchAttachmentBlob: vi.fn(),
  peekAttachmentBlob: vi.fn(() => null),
}))

vi.mock('@/shared/lib/attachment-blob-cache', () => ({
  peekAttachmentBlob,
  fetchAttachmentBlob,
}))

describe('MessageAttachment preview', () => {
  beforeEach(() => {
    fetchAttachmentBlob.mockReset()
    peekAttachmentBlob.mockReset()
    peekAttachmentBlob.mockReturnValue(null)
  })

  it('opens and closes image preview inside the app', async () => {
    fetchAttachmentBlob.mockResolvedValue({
      url: 'blob:test-image',
      mime: 'image/png',
      blob: new Blob(['x'], { type: 'image/png' }),
    })

    const wrapper = mount(MessageAttachment, {
      props: {
        att: {
          type: 'photo',
          status: 'ready',
          download_path: '/api/v1/files/1',
          filename: 'screen.png',
          mime: 'image/png',
        },
        eager: true,
      },
      attachTo: document.body,
    })

    await flushPromises()
    await nextTick()

    await wrapper.find('.message-attachment__image').trigger('click')
    expect(document.body.querySelector('.attachment-preview')).not.toBeNull()

    document.body
      .querySelector('.attachment-preview [title="Закрыть"]')
      ?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()
    expect(document.body.querySelector('.attachment-preview')).toBeNull()

    wrapper.unmount()
  })

  it('opens preview modal from eye button and loads blob on demand', async () => {
    fetchAttachmentBlob.mockResolvedValue({
      url: 'blob:test-pdf',
      mime: 'application/pdf',
      blob: new Blob(['%PDF'], { type: 'application/pdf' }),
    })

    const wrapper = mount(MessageAttachment, {
      props: {
        att: {
          type: 'document',
          status: 'ready',
          download_path: 'chats/1/messages/2/attachments/0',
          filename: 'report.pdf',
          mime: 'application/pdf',
        },
        eager: true,
      },
      attachTo: document.body,
    })

    await nextTick()
    await wrapper.find('[title="Открыть"]').trigger('click')
    expect(document.body.querySelector('.attachment-preview')).not.toBeNull()

    await flushPromises()
    await nextTick()
    expect(fetchAttachmentBlob).toHaveBeenCalled()

    wrapper.unmount()
  })
  it('plays a voice attachment using the authenticated blob', async () => {
    fetchAttachmentBlob.mockResolvedValue({ url: 'blob:test-voice', mime: 'audio/ogg', blob: new Blob(['voice'], {type:'audio/ogg'}) })
    const wrapper = mount(MessageAttachment, {props:{att:{type:'voice',status:'ready',download_path:'/api/v1/files/77',filename:'voice.ogg',mime:'audio/ogg'},eager:true}})
    await flushPromises()
    await wrapper.find('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('audio').attributes('src')).toBe('blob:test-voice')
    expect(wrapper.find('audio').attributes('controls')).toBeDefined()
    wrapper.unmount()
  })

})
