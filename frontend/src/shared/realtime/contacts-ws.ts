import { invalidateContactsQueries } from '@/shared/lib/query-invalidation'
import { extractContactListPatch } from '@/shared/realtime/contact-list-patch'
import { connectRealtime, disconnectRealtime, getRealtimeWS } from '@/shared/realtime/ws-client'

let unsubscribe: (() => void) | undefined

function routeContactFrame(raw: Record<string, unknown>): void {
  const type = raw.type
  if (typeof type !== 'string' || !type.startsWith('contact.')) return

  const payload =
    raw.payload && typeof raw.payload === 'object' && !Array.isArray(raw.payload)
      ? (raw.payload as Record<string, unknown>)
      : {}
  const patch = extractContactListPatch(payload)
  invalidateContactsQueries(patch ? { patch } : undefined)
}

export async function connectContactsRealtime(): Promise<void> {
  await connectRealtime()
  unsubscribe?.()
  unsubscribe = getRealtimeWS().onRaw((raw) => {
    if (!raw || typeof raw !== 'object') return
    routeContactFrame(raw as Record<string, unknown>)
  })
}

export function disconnectContactsRealtime(): void {
  unsubscribe?.()
  unsubscribe = undefined
  disconnectRealtime()
}

/** Visible for tests */
export function resetContactsRealtimeForTests(): void {
  disconnectContactsRealtime()
}

export { routeContactFrame as routeContactFrameForTests }
