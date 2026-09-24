import { mount, flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BlockContactButton from '@/widgets/chat/BlockContactButton.vue'
const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ http: { get, post } }))
const options = { props: { chatId: 7, contactName: 'Клиент' }, attachTo: document.body }
beforeEach(() => { vi.clearAllMocks(); get.mockResolvedValue({ data: { status: 'none' } }) })
describe('global contact blocking', () => {
  it('requires explicit confirmation and shows pending, not success', async () => {
    post.mockResolvedValue({ data: { status: 'pending' } })
    const w = mount(BlockContactButton, options); await flushPromises()
    await w.find('button').trigger('click'); await flushPromises()
    expect(document.body.textContent).toContain('Разблокировки в CRM нет')
    expect(document.body.textContent).toContain('во всех Telegram-ботах')
    expect(post).not.toHaveBeenCalled()
    Array.from(document.querySelectorAll('button')).find(b => b.textContent?.trim() === 'Заблокировать во всех ботах')!.click()
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
    expect(post.mock.calls[0][0]).toBe('/chats/7/telegram-block')
    expect(w.text()).toContain('Блокировка запрошена')
    expect(w.text()).not.toContain('Заблокирован во всех ботах')
    w.unmount()
  })
  it('shows persisted confirmed state and never offers unblock', async () => {
    get.mockResolvedValue({ data: { status: 'blocked', operator: 'Админ', reason: 'спам' } })
    const w = mount(BlockContactButton, options); await flushPromises()
    expect(w.text()).toContain('Заблокирован во всех ботах')
    expect(w.text()).toContain('Админ')
    expect(w.findAll('button')).toHaveLength(0)
    w.unmount()
  })
  it('does not offer global blocking for unsupported contacts', async () => {
    get.mockResolvedValue({ data: { status: 'unsupported' } })
    const w = mount(BlockContactButton, options); await flushPromises()
    expect(w.findAll('button')).toHaveLength(0)
    expect(post).not.toHaveBeenCalled(); w.unmount()
  })
  it('offers retry after failure without claiming success', async () => {
    get.mockResolvedValue({ data: { status: 'failed' } })
    const w = mount(BlockContactButton, options); await flushPromises()
    expect(w.text()).toContain('Мост не подтвердил блокировку')
    expect(w.text()).toContain('Повторить блокировку'); w.unmount()
  })
})
