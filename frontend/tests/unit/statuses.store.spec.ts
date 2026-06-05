import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as leadsApi from '@/features/leads/api'
import { useStatusesStore } from '@/features/statuses/store'

describe('useStatusesStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.restoreAllMocks()
  })

  it('fetches each kind once per session', async () => {
    const listStatuses = vi.spyOn(leadsApi, 'listStatuses').mockResolvedValue({
      items: [
        {
          id: 1,
          code: 'new',
          kind: 'lead_pipeline',
          label: 'Новый',
          color: null,
          sort_order: 0,
          is_active: true,
        },
      ],
    })

    const store = useStatusesStore()
    await store.fetchByKind('lead_pipeline')
    await store.fetchByKind('lead_pipeline')

    expect(listStatuses).toHaveBeenCalledTimes(1)
    expect(store.byKind.lead_pipeline).toHaveLength(1)
  })
})
