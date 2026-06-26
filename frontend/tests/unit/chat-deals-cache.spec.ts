import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  clearChatDealsCache,
  getCachedLeadDetail,
  getChatDealsSnapshot,
  isChatDealsSnapshotFresh,
  pickPreferredLeadId,
  setCachedLeadDetail,
  setChatDealsSnapshot,
} from '@/features/chats/deals-cache'
import { CHAT_SNAPSHOT_FRESH_MS } from '@/features/chats/snapshot-cache'

vi.mock('@/features/leads/api', () => ({
  getLead: vi.fn(),
  listContactLeads: vi.fn(),
}))

function makeLead(id: number, closed = false) {
  return {
    id,
    contact_id: 1,
    group_id: 1,
    bot_id: null,
    chat_id: 10,
    status_id: 1,
    status_code: 'open',
    status_label: 'Открыта',
    bot_name: null,
    bot_code: null,
    title: null,
    closed_at: closed ? '2026-01-01T00:00:00Z' : null,
    created_at: '2026-01-01T00:00:00Z',
  }
}

describe('chat deals cache', () => {
  afterEach(() => {
    clearChatDealsCache()
  })

  it('prefers open lead id', () => {
    const items = [makeLead(1, true), makeLead(2, false), makeLead(3, false)]
    expect(pickPreferredLeadId(items)).toBe(2)
  })

  it('stores and retrieves deals snapshot', () => {
    const items = [makeLead(5)]
    setChatDealsSnapshot(10, items)
    const snapshot = getChatDealsSnapshot(10)
    expect(snapshot?.leadItems).toEqual(items)
    expect(snapshot?.preferredLeadId).toBe(5)
  })

  it('detects fresh snapshots', () => {
    setChatDealsSnapshot(10, [makeLead(1)])
    expect(isChatDealsSnapshotFresh(10)).toBe(true)
    setChatDealsSnapshot(11, [makeLead(2)], 2, {
      fetchedAt: Date.now() - CHAT_SNAPSHOT_FRESH_MS - 1,
    })
    expect(isChatDealsSnapshotFresh(11)).toBe(false)
  })

  it('caches lead detail by id', () => {
    const detail = { ...makeLead(7), updated_at: '2026-01-02T00:00:00Z' }
    setCachedLeadDetail(detail)
    expect(getCachedLeadDetail(7)).toEqual(detail)
  })
})
