/**
 * Shared in-memory cache for /storage/receipts/tree (квитанции + книги продаж).
 * Avoids full refetch every time Storage / Vault picker remounts.
 */

import { listStorageReceiptsTree, type StorageReceiptPeriodGroup } from '@/features/storage/api'
import { getCached, invalidateCached, peekCached, setCached } from '@/shared/lib/stale-cache'

const CACHE_KEY = 'storage:receipts-tree'
const MAX_AGE_MS = 5 * 60_000

let inflight: Promise<{ periods: StorageReceiptPeriodGroup[] }> | null = null

export function peekReceiptsTree(): StorageReceiptPeriodGroup[] | undefined {
  return peekCached<{ periods: StorageReceiptPeriodGroup[] }>(CACHE_KEY)?.periods
}

export async function fetchReceiptsTree(opts?: {
  force?: boolean
}): Promise<{ periods: StorageReceiptPeriodGroup[] }> {
  if (!opts?.force) {
    const fresh = getCached<{ periods: StorageReceiptPeriodGroup[] }>(CACHE_KEY, MAX_AGE_MS)
    if (fresh) return fresh
  }
  if (inflight && !opts?.force) return inflight
  inflight = (async () => {
    try {
      const data = await listStorageReceiptsTree()
      setCached(CACHE_KEY, data)
      return data
    } finally {
      inflight = null
    }
  })()
  return inflight
}

export function invalidateReceiptsTree(): void {
  invalidateCached(CACHE_KEY)
}
