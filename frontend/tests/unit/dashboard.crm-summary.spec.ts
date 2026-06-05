import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as leadsApi from '@/features/leads/api'
import DashboardPage from '@/pages/dashboard/index.vue'

vi.mock('naive-ui', async () => {
  const actual = await vi.importActual<typeof import('naive-ui')>('naive-ui')
  const passthrough = { template: '<div><slot /></div>' }
  return {
    ...actual,
    NSpin: passthrough,
    NStatistic: passthrough,
    NGrid: passthrough,
    NGridItem: passthrough,
    NSpace: passthrough,
    NText: passthrough,
    NButton: { template: '<button><slot /></button>' },
    NIcon: { template: '<span />' },
  }
})

describe('dashboard crm summary', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('loads crm-summary and shows open/closed KPI values', async () => {
    const getSummary = vi.spyOn(leadsApi, 'getCrmDashboardSummary').mockResolvedValue({
      chats_today_count: 5,
      avg_response_minutes: 12.5,
      closed_leads_today_count: 2,
      closed_won_today_count: 1,
      closed_lost_today_count: 1,
      new_clients_today_count: 1,
      open_leads_count: 4,
      closed_today_count: 2,
      by_pipeline_status: [{ status_id: 5, code: 'new', label: 'Новый', count: 3 }],
      by_operator: [
        {
          user_id: 10,
          display_name: 'Оператор',
          chats_today_count: 2,
          avg_response_minutes: 8,
          closed_won_today_count: 1,
          closed_lost_today_count: 0,
          open_leads_count: 1,
        },
      ],
    })

    const wrapper = mount(DashboardPage, {
      global: {
        stubs: { AppCard: { template: '<div><slot /></div>', props: ['title'] } },
      },
    })
    await flushPromises()

    expect(getSummary).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('Чатов сегодня')
    expect(wrapper.text()).toContain('5')
    expect(wrapper.text()).toContain('13 мин')
    expect(wrapper.text()).toContain('Успешных продаж')
    expect(wrapper.text()).toContain('Неуспешных продаж')
    expect(wrapper.text()).toContain('Оператор')
    expect(wrapper.text()).toContain('Успешных')
    expect(wrapper.text()).toContain('Новый')
    expect(wrapper.text()).toContain('3')
  })
})
