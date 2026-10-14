import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), success: vi.fn(), error: vi.fn() }))
vi.mock('@/shared/api/http', () => ({
  http: { get: mocks.get, post: mocks.post },
  AppError: class extends Error {},
}))
vi.mock('naive-ui', () => {
  const passthrough = defineComponent({ setup(_, { slots }) { return () => h('div', slots.default?.()) } })
  return {
    NAlert: passthrough, NButton: passthrough, NEmpty: passthrough,
    NProgress: passthrough, NTag: passthrough, NUpload: passthrough,
    useMessage: () => ({ success: mocks.success, error: mocks.error }),
  }
})
import CompanyChecks from '@/features/lavok-parser/CompanyChecks.vue'

describe('company file checks', () => {
  afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })

  it('shows progress and polls until completion, then stops on unmount', async () => {
    vi.useFakeTimers()
    const job = {
      id: 'a'.repeat(32), filename: 'База.xlsx', status: 'running', total: 10,
      completed: 3, checks_done: 27, checks_total: 90, progress: 30,
      current_inn: '7733475417', source_label: 'Checko', failed_checks: 1,
      rejected_rows: 2, duplicates: 3, created_at: '2026-10-14', updated_at: '2026-10-14',
    }
    mocks.get.mockResolvedValueOnce({ data: { items: [job] } })
      .mockResolvedValue({ data: { items: [{ ...job, status: 'completed_with_errors', progress: 100, result_ready: true }] } })
    const wrapper = mount(CompanyChecks)
    await flushPromises()
    expect(wrapper.text()).toContain('Компаний проверено: 3 / 10')
    expect(wrapper.text()).toContain('Checko, ИНН 7733475417')
    await vi.advanceTimersByTimeAsync(4000)
    await flushPromises()
    expect(wrapper.text()).toContain('Скачать подробный Excel')
    expect(wrapper.text()).toContain('Повторить незавершённые проверки')
    wrapper.unmount()
    const count = mocks.get.mock.calls.length
    await vi.advanceTimersByTimeAsync(60000)
    expect(mocks.get).toHaveBeenCalledTimes(count)
  })
})
