import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  CHAT_SNAPSHOT_CACHE_SIZE,
  CHAT_SNAPSHOT_FRESH_MS,
  clearChatSnapshots,
  getChatSnapshot,
  isChatSnapshotFresh,
  priorityPrefetchChat,
  setChatSnapshot,
  snapshotCacheSize,
} from '@/features/chats/snapshot-cache'

vi.mock('@/features/chats/api', () => ({
  getChat: vi.fn(),
  listMessages: vi.fn(),
}))

function makeSnapshot(id: number) {
  return {
    detail: { id, contact_id: id, contact_name: `c${id}` } as never,
    messages: [],
    nextCursor: null,
  }
}

describe('chat snapshot cache', () => {
  afterEach(() => {
    clearChatSnapshots()
  })

  it('evicts oldest chat when capacity exceeded', () => {
    for (let id = 1; id <= CHAT_SNAPSHOT_CACHE_SIZE + 2; id += 1) {
      setChatSnapshot(id, makeSnapshot(id))
    }
    expect(snapshotCacheSize()).toBe(CHAT_SNAPSHOT_CACHE_SIZE)
    expect(getChatSnapshot(1)).toBeNull()
    expect(getChatSnapshot(2)).toBeNull()
    expect(getChatSnapshot(CHAT_SNAPSHOT_CACHE_SIZE + 2)).not.toBeNull()
  })

  it('touches chat on read (LRU)', () => {
    for (let id = 1; id <= CHAT_SNAPSHOT_CACHE_SIZE; id += 1) {
      setChatSnapshot(id, makeSnapshot(id))
    }
    getChatSnapshot(1)
    setChatSnapshot(CHAT_SNAPSHOT_CACHE_SIZE + 1, makeSnapshot(CHAT_SNAPSHOT_CACHE_SIZE + 1))
    expect(getChatSnapshot(1)).not.toBeNull()
    expect(getChatSnapshot(2)).toBeNull()
  })

  it('detects fresh snapshots', () => {
    setChatSnapshot(7, { ...makeSnapshot(7), fetchedAt: Date.now() })
    expect(isChatSnapshotFresh(7)).toBe(true)
    setChatSnapshot(8, { ...makeSnapshot(8), fetchedAt: Date.now() - CHAT_SNAPSHOT_FRESH_MS - 1 })
    expect(isChatSnapshotFresh(8)).toBe(false)
  })
})
