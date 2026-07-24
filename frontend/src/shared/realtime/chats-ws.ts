import { useChatsStore } from '@/features/chats/store'
import {
  textMatchesMutePhrases,
  useChatNotificationsStore,
} from '@/features/chats/notifications-store'
import { notifyInboundChatMessage } from '@/shared/lib/browser-notifications'
import { invalidateChatsQueries } from '@/shared/lib/query-invalidation'
import { connectRealtime, getRealtimeWS } from '@/shared/realtime/ws-client'

const CHAT_TOPICS = [
  'chat.message.inbound',
  'chat.message.attachment_ready',
  'chat.message.outbound.requested',
  'chat.status_changed',
  'chat.takeover.started',
  'chat.takeover.released',
] as const

let unsubscribers: (() => void)[] = []

export async function connectChatsRealtime(): Promise<void> {
  await connectRealtime()
  teardownChatsHandlers()

  const store = useChatsStore()

  for (const topic of CHAT_TOPICS) {
    unsubscribers.push(
      getRealtimeWS().onTopic(topic, (payload) => {
        routeChatTopic(topic, payload, store)
      }),
    )
  }
}

export function routeChatTopicForTests(
  topic: string,
  payload: Record<string, unknown>,
): void | Promise<void> {
  return routeChatTopic(topic, payload, useChatsStore())
}

function routeChatTopic(
  topic: string,
  payload: Record<string, unknown>,
  store: ReturnType<typeof useChatsStore>,
): void | Promise<void> {
  switch (topic) {
    case 'chat.message.inbound':
      notifyInboundFromPayload(payload, store)
      void store.handleInboundMessage(payload)
      break
    case 'chat.message.attachment_ready':
      void store.handleAttachmentReady(payload)
      break
    case 'chat.message.outbound.requested':
      void store.handleOutboundMessage(payload)
      break
    case 'chat.takeover.started':
      store.handleTakeoverStarted(payload)
      break
    case 'chat.takeover.released':
      store.handleTakeoverReleased(payload)
      break
    case 'chat.status_changed':
      invalidateChatsQueries()
      void store.fetchList(false, { silent: true })
      break
    default:
      break
  }
}

function notifyInboundFromPayload(
  payload: Record<string, unknown>,
  store: ReturnType<typeof useChatsStore>,
): void {
  const chatId = Number(payload.chat_id)
  if (!Number.isFinite(chatId)) return

  const notifications = useChatNotificationsStore()
  const preview =
    typeof payload.text_preview === 'string'
      ? payload.text_preview
      : typeof payload.text === 'string'
        ? payload.text
        : 'Входящее сообщение'

  // В ленту — всегда (кроме активного открытого чата), чтобы не дублировать текущий диалог.
  if (store.currentChatId !== chatId) {
    notifications.pushInbound(payload)
  }

  if (store.currentChatId === chatId) return
  if (!document.hidden) return
  if (
    textMatchesMutePhrases(
      preview,
      notifications.mutePhrases.length ? notifications.mutePhrases : [],
    )
  ) {
    return
  }

  const contactName =
    typeof payload.contact_full_name === 'string'
      ? payload.contact_full_name
      : typeof payload.contact_name === 'string'
        ? payload.contact_name
        : (store.listItems.find((c) => c.id === chatId)?.contact_name ?? 'Новое сообщение')

  notifyInboundChatMessage({
    chatId,
    title: contactName,
    body: preview.slice(0, 120),
  })
}

export function teardownChatsHandlers(): void {
  unsubscribers.forEach((fn) => fn())
  unsubscribers = []
}

/** Test helper */
export function resetChatsRealtimeForTests(): void {
  teardownChatsHandlers()
}
