import type { ChatDetail, ChatMessage } from '@/entities/chat/types'

import * as chatsApi from '@/features/chats/api'
import { prefetchChatDeals } from '@/features/chats/deals-cache'
import { prefetchAttachmentsForMessages } from '@/shared/lib/attachment-blob-cache'

/** Hot chats kept in memory for instant open. */
export const CHAT_SNAPSHOT_CACHE_SIZE = 15
export const CHAT_SNAPSHOT_MESSAGE_LIMIT = 20
/** Skip blocking network refresh when reopening a recently prefetched chat. */
export const CHAT_SNAPSHOT_FRESH_MS = 25_000

export interface ChatSnapshot {
  detail: ChatDetail
  messages: ChatMessage[]
  nextCursor: string | null
  fetchedAt: number
}

const cache = new Map<number, ChatSnapshot>()
const inflight = new Set<number>()
const queue: number[] = []
let activePrefetches = 0
const PREFETCH_CONCURRENCY = 3

function touch(chatId: number, snapshot: ChatSnapshot): void {
  cache.delete(chatId)
  cache.set(chatId, snapshot)
  evictOverflow()
}

function evictOverflow(): void {
  while (cache.size > CHAT_SNAPSHOT_CACHE_SIZE) {
    const oldest = cache.keys().next().value as number | undefined
    if (oldest == null) break
    cache.delete(oldest)
  }
}

export function getChatSnapshot(chatId: number): ChatSnapshot | null {
  const snapshot = cache.get(chatId)
  if (!snapshot) return null
  touch(chatId, snapshot)
  return snapshot
}

export function isChatSnapshotFresh(
  chatId: number,
  maxAgeMs = CHAT_SNAPSHOT_FRESH_MS,
): boolean {
  const snapshot = cache.get(chatId)
  if (!snapshot) return false
  return Date.now() - snapshot.fetchedAt < maxAgeMs
}

export function setChatSnapshot(
  chatId: number,
  snapshot: Omit<ChatSnapshot, 'fetchedAt'> & { fetchedAt?: number },
  options: { prefetchAttachments?: boolean } = {},
): void {
  const messages = snapshot.messages.slice(0, CHAT_SNAPSHOT_MESSAGE_LIMIT)
  touch(chatId, {
    ...snapshot,
    messages,
    fetchedAt: snapshot.fetchedAt ?? Date.now(),
  })
  if (options.prefetchAttachments !== false) {
    prefetchAttachmentsForMessages(messages)
  }
}

export function hasChatSnapshot(chatId: number): boolean {
  return cache.has(chatId)
}

export function clearChatSnapshots(): void {
  cache.clear()
  queue.length = 0
}

function enqueuePrefetch(chatId: number, priority: boolean): void {
  if (cache.has(chatId) || inflight.has(chatId)) return
  const existing = queue.indexOf(chatId)
  if (existing >= 0) {
    queue.splice(existing, 1)
  }
  if (priority) {
    queue.unshift(chatId)
  } else {
    queue.push(chatId)
  }
}

export function scheduleChatSnapshotsPrefetch(
  chatIds: Iterable<number>,
  options: { priority?: boolean } = {},
): void {
  for (const chatId of chatIds) {
    enqueuePrefetch(chatId, options.priority === true)
  }
  drainPrefetchQueue()
}

export function priorityPrefetchChat(chatId: number): void {
  scheduleChatSnapshotsPrefetch([chatId], { priority: true })
}

export function scheduleChatSnapshotsPrefetchIdle(chatIds: Iterable<number>): void {
  const ids = [...chatIds]
  const run = (): void => {
    scheduleChatSnapshotsPrefetch(ids)
  }
  if (typeof requestIdleCallback === 'function') {
    requestIdleCallback(run, { timeout: 2_000 })
  } else {
    setTimeout(run, 0)
  }
}

async function prefetchChat(chatId: number): Promise<void> {
  if (cache.has(chatId) || inflight.has(chatId)) return
  inflight.add(chatId)
  try {
    const [detail, msgs] = await Promise.all([
      chatsApi.getChat(chatId),
      chatsApi.listMessages(chatId, { limit: CHAT_SNAPSHOT_MESSAGE_LIMIT }),
    ])
    setChatSnapshot(chatId, {
      detail,
      messages: msgs.items,
      nextCursor: msgs.next_cursor,
    })
    void prefetchChatDeals(detail)
  } catch {
    /* prefetch is best-effort */
  } finally {
    inflight.delete(chatId)
  }
}

function drainPrefetchQueue(): void {
  while (activePrefetches < PREFETCH_CONCURRENCY && queue.length > 0) {
    const chatId = queue.shift()
    if (chatId == null || cache.has(chatId)) continue
    activePrefetches += 1
    void prefetchChat(chatId).finally(() => {
      activePrefetches -= 1
      drainPrefetchQueue()
    })
  }
}

/** Test helper */
export function snapshotCacheSize(): number {
  return cache.size
}
