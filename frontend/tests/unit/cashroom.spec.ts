import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import Cashroom from '@/pages/cashroom/index.vue'
import { isPhoneChatsOnly } from '@/shared/lib/phone-mode'

const { get, post, error } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), error: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ http: { get, post, put: vi.fn() } }))
vi.mock('naive-ui', async (original) => ({
  ...(await original<object>()),
  useMessage: () => ({ success: vi.fn(), error }),
  useDialog: () => ({ warning: vi.fn() }),
}))
const deal = {
  id: 1,
  client: 'Клиент',
  payer: 'Компания А',
  receiver: 'Компания Б',
  executor: 'Исполнитель',
  entered_on: '2026-09-10',
  due_on: null,
  amount: '300000',
  profit: '3000',
  received: '100000',
  issued: '0',
  receivable: '140000',
  payable: '234000',
  status: 'partial',
}
beforeEach(() => {
  get.mockReset()
  post.mockReset()
  error.mockReset()
  get.mockImplementation((url: string) =>
    Promise.resolve({
      data: url.endsWith('/accounts')
        ? [{ id: 1, name: 'Касса 1', balance: '100000' }]
        : url.endsWith('/deals')
          ? {
              items: [deal],
              summary: {
                count: 1,
                amount: 300000,
                receivable: 140000,
                payable: 234000,
                profit: 3000,
              },
            }
          : { items: [], count: 0 },
    }),
  )
})
it('shows remaining amounts and preserves the payment key when retrying a failed save', async () => {
  const wrapper = mount(Cashroom, { attachTo: document.body })
  await flushPromises()
  expect(wrapper.text()).toContain('Клиент')
  const click = async (text: string) => {
    const button = Array.from(document.querySelectorAll('button')).find(
      (b) => b.textContent?.trim() === text,
    )
    expect(button).toBeTruthy()
    button!.click()
    await flushPromises()
  }
  await click('Получить')
  post
    .mockRejectedValueOnce(new Error('Сеть недоступна'))
    .mockResolvedValueOnce({ data: { id: 2 } })
  const form = document.querySelector('.cash-modal form')!
  form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  expect(error).toHaveBeenCalledWith('Сеть недоступна')
  const first = post.mock.calls[0]![1]
  expect(first.amount).toBe(140000)
  expect(first.deal_id).toBe(1)
  form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
  await flushPromises()
  expect(post.mock.calls[1]![1].operation_key).toBe(first.operation_key)
  wrapper.unmount()
})
it('reports loading errors and lets the user retry', async () => {
  get.mockRejectedValueOnce(new Error('Нет связи'))
  const wrapper = mount(Cashroom)
  await flushPromises()
  expect(wrapper.text()).toContain('Данные не обновлены')
  await wrapper
    .findAll('button')
    .find((b) => b.text() === 'Повторить')!
    .trigger('click')
  await flushPromises()
  expect(wrapper.text()).toContain('Клиент')
  wrapper.unmount()
})
it('keeps the cashroom available to a kesher on a phone', () => {
  expect(isPhoneChatsOnly({ isAccountant: false, isLawyer: false, isKesher: true }, 390)).toBe(
    false,
  )
})
