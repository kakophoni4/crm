import { invalidateContactsQueries } from '@/shared/lib/query-invalidation'
import { connectRealtime, disconnectRealtime, getRealtimeWS } from '@/shared/realtime/ws-client'

let unsubscribe: (() => void) | undefined

export async function connectContactsRealtime(): Promise<void> {
  await connectRealtime()
  unsubscribe?.()
  unsubscribe = getRealtimeWS().onRaw((raw) => {
    if (!raw || typeof raw !== 'object') return
    const type = (raw as { type?: string }).type
    if (typeof type === 'string' && type.startsWith('contact.')) {
      invalidateContactsQueries()
    }
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
