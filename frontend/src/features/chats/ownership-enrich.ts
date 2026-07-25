import type { ChatListItem, ChatMessage } from '@/entities/chat/types'

import type { GroupOwnershipItem, ReplyAuditItem } from '@/entities/contact/types'

import { getReplyAudit } from '@/features/contacts/api'

const REPLY_AUDIT_TTL_MS = 45_000
const REPLY_AUDIT_CACHE_SIZE = 200

type ReplyAuditCacheEntry = {
  items: ReplyAuditItem[]
  fetchedAt: number
}

const replyAuditCache = new Map<string, ReplyAuditCacheEntry>()
const replyAuditInflight = new Map<string, Promise<ReplyAuditItem[]>>()

function sweepReplyAuditCache(now = Date.now()): void {
  for (const [key, entry] of replyAuditCache) {
    if (now - entry.fetchedAt >= REPLY_AUDIT_TTL_MS) {
      replyAuditCache.delete(key)
    }
  }
  while (replyAuditCache.size > REPLY_AUDIT_CACHE_SIZE) {
    const oldest = replyAuditCache.keys().next().value as string | undefined
    if (oldest == null) break
    replyAuditCache.delete(oldest)
  }
}

function touchReplyAudit(key: string, entry: ReplyAuditCacheEntry): void {
  replyAuditCache.delete(key)
  replyAuditCache.set(key, entry)
  sweepReplyAuditCache()
}

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
  const pendingInboundAt = ownership.pending_inbound_at ?? chat.pending_inbound_at ?? null
  const escalatedAt = ownership.escalated_at ?? chat.escalated_at ?? null
  const needsResponse = Boolean(
    ownership.escalated_at
      || ownership.pending_inbound_at
      || chat.escalated_at
      || chat.pending_inbound_at,
  )
  if (
    chat.card_owner_user_id === ownerUserId &&
    chat.card_owner_full_name === ownerFullName &&
    chat.pending_inbound_at === pendingInboundAt &&
    chat.escalated_at === escalatedAt &&
    chat.needs_response === needsResponse &&
    chat.needs_reply === needsResponse
  ) {
    return chat
  }
  return {
    ...chat,
    card_owner_user_id: ownerUserId,
    card_owner_full_name: ownerFullName,
    pending_inbound_at: pendingInboundAt,
    escalated_at: escalatedAt,
    needs_response: needsResponse,
    needs_reply: needsResponse,
  }
}

export function mergeReplyAuditIntoMessages(
  messages: ChatMessage[],
  auditItems: ReplyAuditItem[],
): ChatMessage[] {
  if (!auditItems.length) return messages
  const byMessageId = new Map(auditItems.map((row) => [row.message_id, row]))
  let changed = false
  const next = messages.map((message) => {
    const row = byMessageId.get(message.id)
    if (!row) return message
    const senderUsername =
      message.sender_username?.trim()
      || row.author_username?.trim()
      || row.author_full_name?.trim()
      || message.sender_username
      || null
    if (
      message.is_on_behalf === row.is_on_behalf &&
      message.author_full_name === row.author_full_name &&
      message.author_username === (row.author_username ?? null) &&
      message.card_owner_full_name === row.card_owner_full_name &&
      message.author_user_id === row.author_user_id &&
      message.card_owner_user_id === row.card_owner_user_id &&
      message.sender_username === senderUsername
    ) {
      return message
    }
    changed = true
    return {
      ...message,
      is_on_behalf: row.is_on_behalf,
      author_full_name: row.author_full_name,
      author_username: row.author_username ?? null,
      card_owner_full_name: row.card_owner_full_name,
      author_user_id: row.author_user_id,
      card_owner_user_id: row.card_owner_user_id,
      sender_username: senderUsername,
    }
  })
  return changed ? next : messages
}

async function fetchReplyAuditItems(contactId: number, groupId: number): Promise<ReplyAuditItem[]> {
  const key = ownershipKey(contactId, groupId)
  const now = Date.now()
  const cached = replyAuditCache.get(key)
  if (cached) {
    if (now - cached.fetchedAt < REPLY_AUDIT_TTL_MS) {
      touchReplyAudit(key, cached)
      return cached.items
    }
    replyAuditCache.delete(key)
  }

  let pending = replyAuditInflight.get(key)
  if (!pending) {
    pending = getReplyAudit(contactId, groupId)
      .then((audit) => {
        touchReplyAudit(key, { items: audit.items, fetchedAt: Date.now() })
        return audit.items
      })
      .finally(() => {
        replyAuditInflight.delete(key)
      })
    replyAuditInflight.set(key, pending)
  }
  return pending
}

export async function enrichMessagesWithReplyAudit(
  contactId: number,
  groupId: number | null | undefined,
  messages: ChatMessage[],
): Promise<ChatMessage[]> {
  if (groupId == null) return messages
  try {
    const items = await fetchReplyAuditItems(contactId, groupId)
    return mergeReplyAuditIntoMessages(messages, items)
  } catch {
    return messages
  }
}
