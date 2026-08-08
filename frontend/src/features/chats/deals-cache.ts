import type { ChatDetail } from '@/entities/chat/types'
import {
  CHAT_SNAPSHOT_CACHE_SIZE,
  CHAT_SNAPSHOT_FRESH_MS,
} from '@/features/chats/snapshot-cache'
import { getLead, listContactLeads } from '@/features/leads/api'
import { readLeadDealFields } from '@/features/leads/order-fields'
import type { LeadDetail, LeadListItem } from '@/features/leads/types'

export interface ChatDealsSnapshot {
  leadItems: LeadListItem[]
  preferredLeadId: number | null
  fetchedAt: number
}

const dealsByChatId = new Map<number, ChatDealsSnapshot>()
const leadDetailById = new Map<number, LeadDetail>()
const inflight = new Set<number>()
/** Bound hot lead details similarly to chat snapshots. */
const LEAD_DETAIL_CACHE_SIZE = CHAT_SNAPSHOT_CACHE_SIZE

type NetworkInformation = {
  saveData?: boolean
  effectiveType?: string
}

function isDealsPrefetchAllowed(): boolean {
  if (typeof document !== 'undefined' && document.hidden) return false
  const conn = (typeof navigator !== 'undefined'
    ? (navigator as Navigator & { connection?: NetworkInformation }).connection
    : undefined) as NetworkInformation | undefined
  if (conn?.saveData) return false
  if (conn?.effectiveType === 'slow-2g' || conn?.effectiveType === '2g') return false
  return true
}

function runDealsPrefetchIdle(run: () => void): void {
  if (typeof requestIdleCallback === 'function') {
    requestIdleCallback(run, { timeout: 3_000 })
  } else {
    setTimeout(run, 250)
  }
}

function touch(chatId: number, snapshot: ChatDealsSnapshot): void {
  dealsByChatId.delete(chatId)
  dealsByChatId.set(chatId, snapshot)
  while (dealsByChatId.size > CHAT_SNAPSHOT_CACHE_SIZE) {
    const oldest = dealsByChatId.keys().next().value as number | undefined
    if (oldest == null) break
    dealsByChatId.delete(oldest)
  }
}

function touchLeadDetail(leadId: number, detail: LeadDetail): void {
  leadDetailById.delete(leadId)
  leadDetailById.set(leadId, detail)
  while (leadDetailById.size > LEAD_DETAIL_CACHE_SIZE) {
    const oldest = leadDetailById.keys().next().value as number | undefined
    if (oldest == null) break
    leadDetailById.delete(oldest)
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
  const detail = leadDetailById.get(leadId)
  if (!detail) return null
  touchLeadDetail(leadId, detail)
  return detail
}

export function setCachedLeadDetail(detail: LeadDetail): void {
  touchLeadDetail(detail.id, detail)
  void import('@/features/chats/chats-disk-cache')
    .then((mod) => {
      mod.trackLeadDetailForDisk(detail)
    })
    .catch(() => undefined)
}

export function setChatDealsSnapshot(
  chatId: number,
  leadItems: LeadListItem[],
  preferredLeadId: number | null = pickPreferredLeadId(leadItems),
  options: { fetchedAt?: number } = {},
): void {
  const snapshot: ChatDealsSnapshot = {
    leadItems,
    preferredLeadId,
    fetchedAt: options.fetchedAt ?? Date.now(),
  }
  touch(chatId, snapshot)
  void import('@/features/chats/chats-disk-cache')
    .then((mod) => {
      mod.trackDealsForDisk(chatId, snapshot)
    })
    .catch(() => undefined)
}

/** Prefetch deals from list row — no need to wait for full chat/messages snapshot. */
export async function prefetchChatDealsFromListItem(chat: {
  id: number
  contact_id: number
  assigned_group_id: number | null
}): Promise<void> {
  if (!isDealsPrefetchAllowed()) return
  if (chat.assigned_group_id == null) return
  if (inflight.has(chat.id)) return
  if (isChatDealsSnapshotFresh(chat.id)) return
  inflight.add(chat.id)
  try {
    const data = await listContactLeads(chat.contact_id, {
      group_id: chat.assigned_group_id,
      limit: 100,
    })
    const items = data.items.filter((lead) => lead.chat_id === chat.id)
    const preferredLeadId = pickPreferredLeadId(items)
    setChatDealsSnapshot(chat.id, items, preferredLeadId)
    if (preferredLeadId != null) {
      const lead = await getLead(preferredLeadId)
      setCachedLeadDetail(lead)
      await prefetchOptOrdersIfNeeded(lead)
    }
  } catch {
    /* prefetch is best-effort */
  } finally {
    inflight.delete(chat.id)
  }
}

export function scheduleDealsPrefetchFromList(
  chats: Iterable<{ id: number; contact_id: number; assigned_group_id: number | null }>,
): void {
  runDealsPrefetchIdle(() => {
    if (!isDealsPrefetchAllowed()) return
    // Keep warm-up tiny — each item is listContactLeads + getLead and steals bandwidth from chat open/send.
    const list = [...chats].filter((c) => c.assigned_group_id != null).slice(0, 2)
    let i = 0
    const concurrency = 1
    const workers = Array.from({ length: concurrency }, async () => {
      while (i < list.length) {
        if (!isDealsPrefetchAllowed()) return
        const chat = list[i]
        i += 1
        if (chat) await prefetchChatDealsFromListItem(chat)
      }
    })
    void Promise.all(workers)
  })
}

async function prefetchOptOrdersIfNeeded(detail: LeadDetail): Promise<void> {
  const service = readLeadDealFields(detail.custom_fields).order?.service?.trim()
  if (service !== 'ОПТ') return
  const { prefetchOptOrders } = await import('@/features/chats/payments-cache')
  await prefetchOptOrders(detail.id)
}

export async function prefetchChatDeals(detail: ChatDetail): Promise<void> {
  if (!isDealsPrefetchAllowed()) return
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
      const lead = await getLead(preferredLeadId)
      setCachedLeadDetail(lead)
      await prefetchOptOrdersIfNeeded(lead)
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
