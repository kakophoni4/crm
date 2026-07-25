import { useChatsStore } from '@/features/chats/store'

import { invalidateContactsQueries } from '@/shared/lib/query-invalidation'
import { extractContactListPatch } from '@/shared/realtime/contact-list-patch'

import { connectRealtime, getRealtimeWS } from '@/shared/realtime/ws-client'



const OWNERSHIP_TOPICS = [

  'contact.ownership.assigned',

  'contact.ownership.transferred',

  'contact.ownership.reassigned',

  'contact.escalation.owner_notify',

  'contact.escalation.group_notify',

  'message.replied.on_behalf',
  'contact.transfer.requested',
  'contact.transfer.approved',
  'contact.transfer.declined',
  'contact.transfer.accepted',
  'contact.transfer.rejected',
  'contact.transfer.cancelled',
  'transfer.senior_approved',
  'transfer.senior_declined',
  'transfer.recipient_accepted',
  'transfer.recipient_declined',
  'transfer.cancelled',
] as const



let unsubscribers: (() => void)[] = []



export async function connectOwnershipRealtime(): Promise<void> {

  await connectRealtime()

  teardownOwnershipHandlers()



  const store = useChatsStore()



  for (const topic of OWNERSHIP_TOPICS) {

    unsubscribers.push(

      getRealtimeWS().onTopic(topic, (payload) => {

        routeOwnershipTopic(topic, payload, store)

      }),

    )

  }

}



export function routeOwnershipTopicForTests(

  topic: string,

  payload: Record<string, unknown>,

): void {

  routeOwnershipTopic(topic, payload, useChatsStore())

}



function routeOwnershipTopic(

  topic: string,

  payload: Record<string, unknown>,

  store: ReturnType<typeof useChatsStore>,

): void {

  switch (topic) {

    case 'contact.ownership.assigned':

    case 'contact.ownership.transferred':

    case 'contact.ownership.reassigned':

      store.handleOwnershipChanged(payload)

      {
        const patch = extractContactListPatch(payload)
        // Pass patch object only when present — `{ patch: undefined }` forces full reload.
        if (patch) {
          invalidateContactsQueries({ patch })
        } else {
          invalidateContactsQueries({ reload: true })
        }
      }

      // Row already patched in Pinia; full GET /chats only if chat is missing from list.
      {
        const chatId = Number(payload.chat_id)
        const known =
          Number.isFinite(chatId) && store.listItems.some((c) => c.id === chatId)
        if (!known) {
          store.scheduleSilentListRefresh()
        }
      }

      break

    case 'contact.escalation.owner_notify':

      store.handleEscalationOwnerNotify(payload)

      break

    case 'contact.escalation.group_notify':

      store.handleEscalationGroupNotify(payload)

      break

    case 'message.replied.on_behalf':

      store.handleMessageOnBehalf(payload)

      break

    case 'contact.transfer.requested':
    case 'contact.transfer.approved':
    case 'contact.transfer.declined':
    case 'contact.transfer.accepted':
    case 'contact.transfer.rejected':
    case 'contact.transfer.cancelled':
    case 'transfer.senior_approved':
    case 'transfer.senior_declined':
    case 'transfer.recipient_accepted':
    case 'transfer.recipient_declined':
    case 'transfer.cancelled':
      {
        const patch = extractContactListPatch(payload)
        if (patch) invalidateContactsQueries({ patch })
        else invalidateContactsQueries({ reload: true })
      }
      break

    default:

      break

  }

}



export function teardownOwnershipHandlers(): void {

  unsubscribers.forEach((fn) => fn())

  unsubscribers = []

}



/** Test helper */

export function resetOwnershipRealtimeForTests(): void {

  teardownOwnershipHandlers()

}


