import type { ChatDetail, ChatListItem, ChatMessage } from '@/entities/chat/types'
import type { ChatDealsSnapshot } from '@/features/chats/deals-cache'
import {
  clearChatDealsCache,
  setCachedLeadDetail,
  setChatDealsSnapshot,
} from '@/features/chats/deals-cache'
import {
  CHAT_SNAPSHOT_CACHE_SIZE,
  clearChatSnapshots,
  setChatSnapshot,
} from '@/features/chats/snapshot-cache'
import type { LeadDetail, LeadListItem } from '@/features/leads/types'
import type { OptOrder, OptOrderRegistryItem } from '@/features/leads/opt-types'
import { createDebouncedWriter, readJson, removeJson } from '@/shared/lib/persist-json'
import { useAuthStore } from '@/shared/store/auth'

const NS = 'crm.chats.disk.v1'
const writer = createDebouncedWriter(350)
let hydrating = false

type PersistedList = {
  items: ChatListItem[]
  nextCursor: string | null
  fetchedAt: number
}

type PersistedSnapshotEntry = {
  detail: ChatDetail
  messages: ChatMessage[]
  nextCursor: string | null
  fetchedAt: number
}

type PersistedSnapshots = {
  entries: PersistedSnapshotEntry[]
}

type PersistedDeals = {
  byChat: Array<{ chatId: number; snapshot: ChatDealsSnapshot }>
  leadDetails: LeadDetail[]
}

type PersistedPayments = {
  items: OptOrderRegistryItem[]
  total: number
  fetchedAt: number
}

type PersistedOptOrders = {
  byLead: Array<{ leadId: number; items: OptOrder[]; fetchedAt: number }>
}

function userId(): number | null {
  try {
    return useAuthStore().user?.id ?? null
  } catch {
    return null
  }
}

function key(part: string, uid: number): string {
  return `${NS}.${uid}.${part}`
}

export function persistChatList(items: ChatListItem[], nextCursor: string | null): void {
  const uid = userId()
  if (uid == null) return
  writer.schedule(key('list', uid), {
    items: items.slice(0, 80),
    nextCursor,
    fetchedAt: Date.now(),
  } satisfies PersistedList)
}

export function peekPersistedChatList(): PersistedList | null {
  const uid = userId()
  if (uid == null) return null
  const data = readJson<PersistedList>(key('list', uid))
  if (!data?.items?.length) return null
  return data
}

export function persistSnapshotsToDisk(): void {
  const uid = userId()
  if (uid == null) return
  const entries: PersistedSnapshotEntry[] = []
  // Walk LRU order via repeated get is expensive; rebuild from known ids by probing cache size.
  // Snapshot cache doesn't expose entries — collect by reading recently touched via a side map.
  const collected = collectSnapshotsForPersist()
  for (const row of collected.slice(-CHAT_SNAPSHOT_CACHE_SIZE)) {
    entries.push(row)
  }
  writer.schedule(key('snapshots', uid), { entries } satisfies PersistedSnapshots)
}

/** Filled by snapshot-cache on set; keeps disk export cheap. */
const snapshotIndex = new Map<number, PersistedSnapshotEntry>()

export function trackSnapshotForDisk(
  chatId: number,
  snapshot: {
    detail: ChatDetail
    messages: ChatMessage[]
    nextCursor: string | null
    fetchedAt: number
  },
): void {
  snapshotIndex.delete(chatId)
  snapshotIndex.set(chatId, {
    detail: snapshot.detail,
    messages: snapshot.messages.slice(0, 50),
    nextCursor: snapshot.nextCursor,
    fetchedAt: snapshot.fetchedAt,
  })
  while (snapshotIndex.size > CHAT_SNAPSHOT_CACHE_SIZE) {
    const oldest = snapshotIndex.keys().next().value as number | undefined
    if (oldest == null) break
    snapshotIndex.delete(oldest)
  }
  if (!hydrating) persistSnapshotsToDisk()
}

function collectSnapshotsForPersist(): PersistedSnapshotEntry[] {
  return [...snapshotIndex.values()]
}

export function persistDealsToDisk(): void {
  const uid = userId()
  if (uid == null) return
  const byChat: PersistedDeals['byChat'] = []
  for (const [chatId, snapshot] of dealsSnapshotIndex) {
    byChat.push({ chatId, snapshot })
  }
  writer.schedule(key('deals', uid), {
    byChat: byChat.slice(-CHAT_SNAPSHOT_CACHE_SIZE),
    leadDetails: [...leadDetailIndex.values()].slice(-CHAT_SNAPSHOT_CACHE_SIZE),
  } satisfies PersistedDeals)
}

const dealsIndex = new Set<number>()
const dealsSnapshotIndex = new Map<number, ChatDealsSnapshot>()
const leadDetailIndex = new Map<number, LeadDetail>()

export function trackDealsForDisk(
  chatId: number,
  snapshot: ChatDealsSnapshot,
  leadDetail?: LeadDetail | null,
): void {
  dealsIndex.add(chatId)
  dealsSnapshotIndex.set(chatId, snapshot)
  if (leadDetail) leadDetailIndex.set(leadDetail.id, leadDetail)
  if (!hydrating) persistDealsToDisk()
}

export function trackLeadDetailForDisk(detail: LeadDetail): void {
  leadDetailIndex.set(detail.id, detail)
  if (!hydrating) persistDealsToDisk()
}

let paymentsMemory: PersistedPayments | null = null
const optOrdersMemory = new Map<number, { items: OptOrder[]; fetchedAt: number }>()

export function setPaymentsRegistryCache(
  items: OptOrderRegistryItem[],
  total: number,
): void {
  paymentsMemory = { items, total, fetchedAt: Date.now() }
  const uid = userId()
  if (uid == null) return
  writer.schedule(key('payments', uid), paymentsMemory)
}

export function getPaymentsRegistryCache(): PersistedPayments | null {
  if (paymentsMemory) return paymentsMemory
  const uid = userId()
  if (uid == null) return null
  paymentsMemory = readJson<PersistedPayments>(key('payments', uid))
  return paymentsMemory
}

export function setOptOrdersCache(leadId: number, items: OptOrder[]): void {
  const row = { items, fetchedAt: Date.now() }
  optOrdersMemory.set(leadId, row)
  const uid = userId()
  if (uid == null) return
  const byLead = [...optOrdersMemory.entries()]
    .slice(-60)
    .map(([id, value]) => ({ leadId: id, items: value.items, fetchedAt: value.fetchedAt }))
  writer.schedule(key('optOrders', uid), { byLead } satisfies PersistedOptOrders)
}

export function getOptOrdersCache(leadId: number): { items: OptOrder[]; fetchedAt: number } | null {
  const mem = optOrdersMemory.get(leadId)
  if (mem) return mem
  const uid = userId()
  if (uid == null) return null
  const disk = readJson<PersistedOptOrders>(key('optOrders', uid))
  if (!disk?.byLead) return null
  for (const row of disk.byLead) {
    optOrdersMemory.set(row.leadId, { items: row.items, fetchedAt: row.fetchedAt })
  }
  return optOrdersMemory.get(leadId) ?? null
}

export function isOptOrdersCacheFresh(leadId: number, maxAgeMs = 120_000): boolean {
  const row = getOptOrdersCache(leadId)
  if (!row) return false
  return Date.now() - row.fetchedAt < maxAgeMs
}

export function isPaymentsRegistryFresh(maxAgeMs = 120_000): boolean {
  const row = getPaymentsRegistryCache()
  if (!row) return false
  return Date.now() - row.fetchedAt < maxAgeMs
}

/** Hydrate in-memory caches from localStorage for instant UI on revisit. */
export function hydrateChatsDiskCaches(): void {
  const uid = userId()
  if (uid == null) return

  hydrating = true
  try {
    const snapshots = readJson<PersistedSnapshots>(key('snapshots', uid))
    if (snapshots?.entries?.length) {
      for (const entry of snapshots.entries) {
        if (entry?.detail?.id == null) continue
        setChatSnapshot(
          entry.detail.id,
          {
            detail: entry.detail,
            messages: entry.messages ?? [],
            nextCursor: entry.nextCursor ?? null,
            fetchedAt: entry.fetchedAt ?? 0,
          },
          { prefetchAttachments: false },
        )
        trackSnapshotForDisk(entry.detail.id, {
          detail: entry.detail,
          messages: entry.messages ?? [],
          nextCursor: entry.nextCursor ?? null,
          fetchedAt: entry.fetchedAt ?? 0,
        })
      }
    }

    const deals = readJson<PersistedDeals>(key('deals', uid))
    if (deals?.byChat?.length) {
      for (const row of deals.byChat) {
        if (row?.chatId == null || !row.snapshot) continue
        setChatDealsSnapshot(
          row.chatId,
          row.snapshot.leadItems as LeadListItem[],
          row.snapshot.preferredLeadId,
          { fetchedAt: row.snapshot.fetchedAt },
        )
        dealsIndex.add(row.chatId)
      }
    }
    if (deals?.leadDetails?.length) {
      for (const detail of deals.leadDetails) {
        if (detail?.id == null) continue
        setCachedLeadDetail(detail)
        leadDetailIndex.set(detail.id, detail)
      }
    }

    paymentsMemory = readJson<PersistedPayments>(key('payments', uid))
    const opt = readJson<PersistedOptOrders>(key('optOrders', uid))
    if (opt?.byLead?.length) {
      for (const row of opt.byLead) {
        optOrdersMemory.set(row.leadId, { items: row.items, fetchedAt: row.fetchedAt })
      }
    }
  } finally {
    hydrating = false
  }
}

export function clearChatsDiskCaches(): void {
  writer.clear()
  const uid = userId()
  snapshotIndex.clear()
  dealsIndex.clear()
  dealsSnapshotIndex.clear()
  leadDetailIndex.clear()
  paymentsMemory = null
  optOrdersMemory.clear()
  clearChatSnapshots()
  clearChatDealsCache()
  if (uid == null) return
  removeJson(key('list', uid))
  removeJson(key('snapshots', uid))
  removeJson(key('deals', uid))
  removeJson(key('payments', uid))
  removeJson(key('optOrders', uid))
}

/** Force flush pending writes (tests / beforeunload). */
export function flushChatsDiskCaches(): void {
  writer.flush()
}
