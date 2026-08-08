/**
 * Cache «есть ли квитанции / книги» по заявке — чтобы кнопки не мигали
 * и API не дёргался при каждом выборе вкладки заявки.
 */

interface OrderDocsAvailability {
  receipts: boolean
  salesBooks: boolean
  at: number
}

type OrderDocsFlags = { receipts: boolean; salesBooks: boolean }

const store = new Map<number, OrderDocsAvailability>()
const MAX_AGE_MS = 5 * 60_000
const inflight = new Map<number, Promise<OrderDocsFlags>>()

export function peekOrderDocsAvailability(orderId: number): OrderDocsFlags | null {
  const hit = store.get(orderId)
  if (!hit) return null
  return { receipts: hit.receipts, salesBooks: hit.salesBooks }
}

export function isOrderDocsAvailabilityFresh(orderId: number): boolean {
  const hit = store.get(orderId)
  if (!hit) return false
  return Date.now() - hit.at < MAX_AGE_MS
}

export function setOrderDocsAvailability(orderId: number, value: OrderDocsFlags): void {
  store.set(orderId, { ...value, at: Date.now() })
}

export async function loadOrderDocsAvailability(
  orderId: number,
  loader: () => Promise<OrderDocsFlags>,
  opts?: { force?: boolean },
): Promise<OrderDocsFlags> {
  if (!opts?.force && isOrderDocsAvailabilityFresh(orderId)) {
    return peekOrderDocsAvailability(orderId)!
  }
  const existing = inflight.get(orderId)
  if (existing && !opts?.force) return existing
  const run = (async () => {
    try {
      const value = await loader()
      setOrderDocsAvailability(orderId, value)
      return value
    } finally {
      inflight.delete(orderId)
    }
  })()
  inflight.set(orderId, run)
  return run
}
