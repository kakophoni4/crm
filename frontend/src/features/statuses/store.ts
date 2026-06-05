import { defineStore } from 'pinia'
import { ref } from 'vue'

import { listStatuses } from '@/features/leads/api'
import type { StatusKind, StatusOption } from '@/features/leads/types'

const inflight = new Map<StatusKind | 'all', Promise<StatusOption[]>>()

export const useStatusesStore = defineStore('statuses', () => {
  const byKind = ref<Partial<Record<StatusKind, StatusOption[]>>>({})

  async function fetchByKind(kind: StatusKind): Promise<StatusOption[]> {
    const cached = byKind.value[kind]
    if (cached) return cached

    let pending = inflight.get(kind)
    if (!pending) {
      pending = listStatuses({ kind }).then((response) => response.items)
      inflight.set(kind, pending)
    }

    try {
      const items = await pending
      byKind.value = { ...byKind.value, [kind]: items }
      return items
    } finally {
      inflight.delete(kind)
    }
  }

  function reset(): void {
    byKind.value = {}
    inflight.clear()
  }

  return { byKind, fetchByKind, reset }
})
