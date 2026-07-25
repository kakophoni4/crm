import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  createDebouncedFlush,
  invalidateContactsQueries,
  onContactsInvalidate,
} from '@/shared/lib/query-invalidation'
import { extractContactListPatch } from '@/shared/realtime/contact-list-patch'

describe('query-invalidation contacts', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  it('coalesces debounced reload notifications', () => {
    const reloads: number[] = []
    const stop = onContactsInvalidate((event) => {
      if (event.reload) reloads.push(Date.now())
    })

    invalidateContactsQueries()
    invalidateContactsQueries()
    invalidateContactsQueries()
    expect(reloads).toEqual([])

    vi.advanceTimersByTime(400)
    expect(reloads).toHaveLength(1)

    stop()
    vi.useRealTimers()
  })

  it('delivers patch immediately without scheduling reload', () => {
    const patches: number[] = []
    const reloads: number[] = []
    const stop = onContactsInvalidate((event) => {
      if (event.patch) patches.push(event.patch.contactId)
      if (event.reload) reloads.push(1)
    })

    invalidateContactsQueries({
      patch: { contactId: 7, patch: { full_name: 'Ann' } },
    })
    expect(patches).toEqual([7])
    expect(reloads).toEqual([])

    vi.advanceTimersByTime(400)
    expect(reloads).toEqual([])

    stop()
    vi.useRealTimers()
  })

  it('patch + reload still debounces full list refresh', () => {
    const reloads: number[] = []
    const stop = onContactsInvalidate((event) => {
      if (event.reload) reloads.push(1)
    })

    invalidateContactsQueries({
      patch: { contactId: 7, patch: { full_name: 'Ann' } },
      reload: true,
    })
    expect(reloads).toEqual([])
    vi.advanceTimersByTime(400)
    expect(reloads).toEqual([1])

    stop()
    vi.useRealTimers()
  })

  it('immediate reload skips debounce', () => {
    const reloads: number[] = []
    const stop = onContactsInvalidate((event) => {
      if (event.reload) reloads.push(1)
    })

    invalidateContactsQueries({ immediate: true })
    expect(reloads).toEqual([1])

    stop()
    vi.useRealTimers()
  })
})

describe('createDebouncedFlush', () => {
  it('runs only the latest scheduled callback', () => {
    vi.useFakeTimers()
    const runs: string[] = []
    const debouncer = createDebouncedFlush(300)

    debouncer.schedule(() => runs.push('a'))
    debouncer.schedule(() => runs.push('b'))
    vi.advanceTimersByTime(300)
    expect(runs).toEqual(['b'])

    vi.useRealTimers()
  })
})

describe('extractContactListPatch', () => {
  it('maps contact_full_name from ownership payloads', () => {
    expect(
      extractContactListPatch({
        contact_id: 12,
        contact_full_name: 'New Name',
      }),
    ).toEqual({
      contactId: 12,
      patch: { full_name: 'New Name' },
    })
  })

  it('returns undefined when no patchable fields exist', () => {
    expect(extractContactListPatch({ contact_id: 3, group_id: 1 })).toBeUndefined()
  })
})
