import type { ChatListItem, ChatMessage } from '@/entities/chat/types'

import type { GroupOwnershipItem, ReplyAuditItem } from '@/entities/contact/types'

import { getReplyAudit } from '@/features/contacts/api'



export function ownershipKey(contactId: number, groupId: number): string {

  return `${contactId}:${groupId}`

}



export function applyOwnershipToChat(

  chat: ChatListItem,

  ownership: GroupOwnershipItem | undefined,

): ChatListItem {

  if (!ownership) return chat

  const ownerUserId = ownership.owner_user_id ?? chat.card_owner_user_id ?? null

  let ownerFullName = ownership.owner_full_name?.trim() || null

  if (!ownerFullName && ownerUserId != null && ownerUserId === chat.card_owner_user_id) {

    ownerFullName = chat.card_owner_full_name?.trim() || null

  }

  return {

    ...chat,

    card_owner_user_id: ownerUserId,

    card_owner_full_name: ownerFullName,

    pending_inbound_at: ownership.pending_inbound_at ?? chat.pending_inbound_at ?? null,

    escalated_at: ownership.escalated_at ?? chat.escalated_at ?? null,

    needs_response: Boolean(
      ownership.escalated_at
        || ownership.pending_inbound_at
        || chat.escalated_at
        || chat.pending_inbound_at,
    ),

    needs_reply: Boolean(
      ownership.escalated_at
        || ownership.pending_inbound_at
        || chat.escalated_at
        || chat.pending_inbound_at,
    ),

  }

}



export function mergeReplyAuditIntoMessages(

  messages: ChatMessage[],

  auditItems: ReplyAuditItem[],

): ChatMessage[] {

  if (!auditItems.length) return messages

  const byMessageId = new Map(auditItems.map((row) => [row.message_id, row]))

  return messages.map((message) => {

    const row = byMessageId.get(message.id)

    if (!row) return message

    return {

      ...message,

      is_on_behalf: row.is_on_behalf,

      author_full_name: row.author_full_name,

      author_username: row.author_username ?? null,

      card_owner_full_name: row.card_owner_full_name,

      author_user_id: row.author_user_id,

      card_owner_user_id: row.card_owner_user_id,

      sender_username:
        message.sender_username?.trim()
        || row.author_username?.trim()
        || row.author_full_name?.trim()
        || message.sender_username
        || null,

    }

  })

}



export async function enrichMessagesWithReplyAudit(

  contactId: number,

  groupId: number | null | undefined,

  messages: ChatMessage[],

): Promise<ChatMessage[]> {

  if (groupId == null) return messages

  try {

    const audit = await getReplyAudit(contactId, groupId)

    return mergeReplyAuditIntoMessages(messages, audit.items)

  } catch {

    return messages

  }

}


