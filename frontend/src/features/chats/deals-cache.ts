import type { ChatDetail } from '@/entities/chat/types'
import {
  CHAT_SNAPSHOT_CACHE_SIZE,
  CHAT_SNAPSHOT_FRESH_MS,
} from '@/features/chats/snapshot-cache'
import { getLead, listContactLeads } from '@/features/leads/api'
import type { LeadDetail, LeadListItem } from '@/features/leads/types'

export interface ChatDealsSnapshot {
  leadItems: LeadListItem[]
  preferredLeadId: number | null
  fetchedAt: number
}

const dealsByChatId = new Map<number, ChatDealsSnapshot>()
const leadDetailById = new Map<number, LeadDetail>()
const inflight = new Set<number>()

function touch(chatId: number, snapshot: ChatDealsSnapshot): void {
  dealsByChatId.delete(chatId)
  dealsByChatId.set(chatId, snapshot)
  while (dealsByChatId.size > CHAT_SNAPSHOT_CACHE_SIZE) {
    const oldest = dealsByChatId.keys().next().value as number | undefined
    if (oldest == null) break
    dealsByChatId.delete(oldest)
  }
}

export function pickPreferredLeadId(items: LeadListItem[]): number | null {
  return items.find((lead) => lead.closed_at == null)?.id ?? items[0]?.id ?? null
}

export function getChatDealsSnapshot(chatId: number): ChatDealsSnapshot | null {
  const snapshot = dealsByChatId.get(chatId)
  if (!snapshot) return null
  touch(chatId, snapshot)
  return snapshot
}

export function isChatDealsSnapshotFresh(
  chatId: number,
  maxAgeMs = CHAT_SNAPSHOT_FRESH_MS,
): boolean {
  const snapshot = dealsByChatId.get(chatId)
  if (!snapshot) return false
  return Date.now() - snapshot.fetchedAt < maxAgeMs
}

export function getCachedLeadDetail(leadId: number): LeadDetail | null {
  return leadDetailById.get(leadId) ?? null
}

export function setCachedLeadDetail(detail: LeadDetail): void {
  leadDetailById.set(detail.id, detail)
}

export function setChatDealsSnapshot(
  chatId: number,
  leadItems: LeadListItem[],
  preferredLeadId: number | null = pickPreferredLeadId(leadItems),
  options: { fetchedAt?: number } = {},
): void {
  touch(chatId, {
    leadItems,
    preferredLeadId,
    fetchedAt: options.fetchedAt ?? Date.now(),
  })
}

export async function prefetchChatDeals(detail: ChatDetail): Promise<void> {
  const chatId = detail.id
  if (detail.assigned_group_id == null) return
  if (inflight.has(chatId)) return
  inflight.add(chatId)
  try {
    const data = await listContactLeads(detail.contact_id, {
      group_id: detail.assigned_group_id,
      limit: 100,
    })
    const items = data.items.filter((lead) => lead.chat_id === chatId)
    const preferredLeadId = pickPreferredLeadId(items)
    setChatDealsSnapshot(chatId, items, preferredLeadId)
    if (preferredLeadId != null) {
      setCachedLeadDetail(await getLead(preferredLeadId))
    }
  } catch {
    /* prefetch is best-effort */
  } finally {
    inflight.delete(chatId)
  }
}

export function invalidateChatDeals(chatId: number): void {
  dealsByChatId.delete(chatId)
}

/** Test helper */
export function clearChatDealsCache(): void {
  dealsByChatId.clear()
  leadDetailById.clear()
  inflight.clear()
}
