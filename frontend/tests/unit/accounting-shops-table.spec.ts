import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ShopsTable from '@/features/accounting/ShopsTable.vue'

const { patch, error } = vi.hoisted(() => ({ patch: vi.fn(), error: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ http: { patch }, AppError: class extends Error {} }))
vi.mock('naive-ui', async (original) => ({
  ...(await original<object>()),
  useMessage: () => ({ success: vi.fn(), error }),
}))
const row = {
  unit_id: 1,
  inn: '1234567890',
  name: 'Лавка',
  is_active: true,
  accountant_full_name: 'Бухгалтер',
  shop_fields: { fns: '1234', comment: 'Было' },
}
function render() {
  return mount(ShopsTable, { props: { rows: [row] } })
}
beforeEach(() => {
  patch.mockReset()
  error.mockReset()
})
describe('accounting shop row editing', () => {
  it('saves only the changed field and requests a shared-data refresh', async () => {
    patch.mockResolvedValue({ data: {} })
    const wrapper = render()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Заполнить')!
      .trigger('click')
    await wrapper.get('input[aria-label="Комментарий"]').setValue('Новое')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Сохранить')!
      .trigger('click')
    await flushPromises()
    expect(patch).toHaveBeenCalledWith('/accounting/units/1/card', { comment: 'Новое' })
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })
  it('keeps entered values on a failed save', async () => {
    patch.mockRejectedValue(new Error('offline'))
    const wrapper = render()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Заполнить')!
      .trigger('click')
    await wrapper.get('input[aria-label="Комментарий"]').setValue('Не потерять')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Сохранить')!
      .trigger('click')
    await flushPromises()
    expect((wrapper.get('input[aria-label="Комментарий"]').element as HTMLInputElement).value).toBe(
      'Не потерять',
    )
    expect(wrapper.emitted('saved')).toBeUndefined()
  })
  it('cancels without writing', async () => {
    const wrapper = render()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Заполнить')!
      .trigger('click')
    await wrapper.get('input[aria-label="Комментарий"]').setValue('Отмена')
    await wrapper
      .findAll('button')
      .find((b) => b.text() === 'Отмена')!
      .trigger('click')
    expect(patch).not.toHaveBeenCalled()
    expect(wrapper.find('input').exists()).toBe(false)
  })
})

it('keeps edits across column groups and saves them together', async () => {
  patch.mockResolvedValue({ data: {} })
  const wrapper = render()
  const click = async (label: string) =>
    wrapper
      .findAll('button')
      .find((b) => b.text() === label)!
      .trigger('click')
  await click('Заполнить')
  await wrapper.get('input[aria-label="Комментарий"]').setValue('Комментарий изменён')
  await click('ЭЦП и ЭДО')
  expect(wrapper.find('input[aria-label="Комментарий"]').exists()).toBe(false)
  await wrapper.get('input[aria-label="СБИС"]').setValue('Активен')
  await click('Основное')
  expect((wrapper.get('input[aria-label="Комментарий"]').element as HTMLInputElement).value).toBe(
    'Комментарий изменён',
  )
  await click('Сохранить')
  await flushPromises()
  expect(patch).toHaveBeenCalledWith('/accounting/units/1/card', {
    comment: 'Комментарий изменён',
    sbis: 'Активен',
  })
})
