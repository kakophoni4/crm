import {
  getOptOrdersCache,
  getPaymentsRegistryCache,
  isOptOrdersCacheFresh,
  isPaymentsRegistryFresh,
  setOptOrdersCache,
  setPaymentsRegistryCache,
} from '@/features/chats/chats-disk-cache'
import { listOptOrders, listOptOrdersRegistry } from '@/features/leads/opt-api'
import type { OptOrder, OptOrderRegistryItem } from '@/features/leads/opt-types'

let paymentsInflight: Promise<void> | null = null
const optInflight = new Map<number, Promise<void>>()

export function peekPaymentsRegistry(): {
  items: OptOrderRegistryItem[]
  total: number
  fetchedAt: number
} | null {
  return getPaymentsRegistryCache()
}

export async function prefetchPaymentsRegistry(force = false): Promise<void> {
  if (!force && isPaymentsRegistryFresh()) return
  if (paymentsInflight) return paymentsInflight
  paymentsInflight = (async () => {
    try {
      const data = await listOptOrdersRegistry({
        payment_status: 'unpaid,partial',
        open_only: true,
        limit: 100,
        offset: 0,
      })
      setPaymentsRegistryCache(data.items, data.total)
    } catch {
      /* best-effort */
    } finally {
      paymentsInflight = null
    }
  })()
  return paymentsInflight
}

export function peekOptOrders(leadId: number): OptOrder[] | null {
  return getOptOrdersCache(leadId)?.items ?? null
}

export async function prefetchOptOrders(leadId: number, force = false): Promise<void> {
  if (!force && isOptOrdersCacheFresh(leadId)) return
  const existing = optInflight.get(leadId)
  if (existing) return existing
  const run = (async () => {
    try {
      const items = await listOptOrders(leadId)
      setOptOrdersCache(leadId, items)
    } catch {
      /* best-effort */
    } finally {
      optInflight.delete(leadId)
    }
  })()
  optInflight.set(leadId, run)
  return run
}
