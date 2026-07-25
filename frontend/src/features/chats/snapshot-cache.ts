import type { ChatDetail, ChatMessage } from '@/entities/chat/types'

import * as chatsApi from '@/features/chats/api'
import { prefetchChatDeals } from '@/features/chats/deals-cache'
import { prefetchAttachmentsForMessages } from '@/shared/lib/attachment-blob-cache'

/** Hot chats kept in memory for instant open. */
export const CHAT_SNAPSHOT_CACHE_SIZE = 40
export const CHAT_SNAPSHOT_MESSAGE_LIMIT = 50
/** Skip blocking network refresh when reopening a recently prefetched chat. */
export const CHAT_SNAPSHOT_FRESH_MS = 120_000

export interface ChatSnapshot {
  detail: ChatDetail
  messages: ChatMessage[]
  nextCursor: string | null
  fetchedAt: number
}

interface PrefetchQueueItem {
  chatId: number
  priority: boolean
}

const cache = new Map<number, ChatSnapshot>()
const inflight = new Set<number>()
const queue: PrefetchQueueItem[] = []
let activePrefetches = 0
/** Keep low — each prefetch is getChat + listMessages + attachment warm-up. */
const PREFETCH_CONCURRENCY = 2

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
  options: {
    prefetchAttachments?: boolean
    attachmentPriority?: 'high' | 'normal'
  } = {},
): void {
  // Chronological oldest→newest: keep the tip (newest), not the head.
  const messages = snapshot.messages.slice(-CHAT_SNAPSHOT_MESSAGE_LIMIT)
  const full: ChatSnapshot = {
    ...snapshot,
    messages,
    fetchedAt: snapshot.fetchedAt ?? Date.now(),
  }
  touch(chatId, full)
  if (options.prefetchAttachments !== false) {
    prefetchAttachmentsForMessages(messages, {
      priority: options.attachmentPriority ?? 'normal',
    })
  }
  void import('@/features/chats/chats-disk-cache')
    .then((mod) => {
      mod.trackSnapshotForDisk(chatId, full)
    })
    .catch(() => undefined)
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
  const existing = queue.findIndex((item) => item.chatId === chatId)
  if (existing >= 0) {
    const item = queue.splice(existing, 1)[0]
    if (item) {
      queue.unshift({ chatId, priority: item.priority || priority })
      drainPrefetchQueue()
      return
    }
  }
  if (priority) {
    queue.unshift({ chatId, priority: true })
  } else {
    queue.push({ chatId, priority: false })
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

/** Wait until a snapshot appears (e.g. after priority prefetch), or timeout. */
export function waitForChatSnapshot(
  chatId: number,
  timeoutMs = 4_000,
): Promise<ChatSnapshot | null> {
  const existing = cache.get(chatId)
  if (existing) {
    touch(chatId, existing)
    return Promise.resolve(existing)
  }
  return new Promise((resolve) => {
    const started = Date.now()
    const tick = (): void => {
      const snapshot = cache.get(chatId)
      if (snapshot) {
        touch(chatId, snapshot)
        resolve(snapshot)
        return
      }
      if (Date.now() - started >= timeoutMs) {
        resolve(null)
        return
      }
      window.setTimeout(tick, 50)
    }
    tick()
  })
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

async function prefetchChat(chatId: number, priority: boolean): Promise<void> {
  if (cache.has(chatId) || inflight.has(chatId)) return
  inflight.add(chatId)
  try {
    const [detail, msgs] = await Promise.all([
      chatsApi.getChat(chatId),
      chatsApi.listMessages(chatId, { limit: CHAT_SNAPSHOT_MESSAGE_LIMIT }),
    ])
    const attachmentPriority = priority ? 'high' : 'normal'
    prefetchAttachmentsForMessages(msgs.items, { priority: attachmentPriority })
    setChatSnapshot(
      chatId,
      {
        detail,
        messages: msgs.items,
        nextCursor: msgs.next_cursor,
      },
      { prefetchAttachments: false },
    )
    void prefetchChatDeals(detail)
  } catch {
    /* prefetch is best-effort */
  } finally {
    inflight.delete(chatId)
  }
}

function drainPrefetchQueue(): void {
  while (activePrefetches < PREFETCH_CONCURRENCY && queue.length > 0) {
    const item = queue.shift()
    if (item == null || cache.has(item.chatId)) continue
    activePrefetches += 1
    void prefetchChat(item.chatId, item.priority).finally(() => {
      activePrefetches -= 1
      drainPrefetchQueue()
    })
  }
}

/** Test helper */
export function snapshotCacheSize(): number {
  return cache.size
}
