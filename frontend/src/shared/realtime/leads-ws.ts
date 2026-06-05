import { useChatsStore } from '@/features/chats/store'
import { connectRealtime, getRealtimeWS } from '@/shared/realtime/ws-client'

const LEAD_TOPICS = ['lead.created', 'lead.closed', 'lead.status_changed'] as const

let unsubscribers: (() => void)[] = []

export async function connectLeadsRealtime(): Promise<void> {
  await connectRealtime()
  teardownLeadsHandlers()

  const store = useChatsStore()

  for (const topic of LEAD_TOPICS) {
    unsubscribers.push(
      getRealtimeWS().onTopic(topic, (payload) => {
        routeLeadTopic(topic, payload, store)
      }),
    )
  }
}

export function routeLeadTopicForTests(
  topic: string,
  payload: Record<string, unknown>,
): void | Promise<void> {
  return routeLeadTopic(topic, payload, useChatsStore())
}

function routeLeadTopic(
  topic: string,
  payload: Record<string, unknown>,
  store: ReturnType<typeof useChatsStore>,
): void | Promise<void> {
  switch (topic) {
    case 'lead.created':
    case 'lead.closed':
    case 'lead.status_changed':
      void store.handleLeadEvent(topic, payload)
      break
    default:
      break
  }
}

export function teardownLeadsHandlers(): void {
  unsubscribers.forEach((fn) => fn())
  unsubscribers = []
}

export function resetLeadsRealtimeForTests(): void {
  teardownLeadsHandlers()
}
