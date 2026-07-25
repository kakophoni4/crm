import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { http } from '@/shared/api/http'
import {
  clearAttachmentBlobCache,
  collectReadyAttachmentPaths,
  fetchAttachmentBlob,
  peekAttachmentBlobUrl,
  prefetchAttachmentBlobUrls,
  setAttachmentBlobCacheLimitsForTests,
} from '@/shared/lib/attachment-blob-cache'

vi.mock('@/shared/api/http', () => ({
  http: {
    get: vi.fn((path: string) => {
      const size = Number(String(path).split('/').pop())
      const bytes = Number.isFinite(size) && size > 0 ? size : 1
      return Promise.resolve({
        data: new Blob([new Uint8Array(bytes)], { type: 'image/png' }),
      })
    }),
  },
}))

describe('attachment blob cache prefetch', () => {
  const createObjectURL = vi.spyOn(URL, 'createObjectURL')
  const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL')

  beforeEach(() => {
    createObjectURL.mockImplementation((blob) => `blob:${(blob as Blob).size}`)
  })

  afterEach(() => {
    clearAttachmentBlobCache()
    vi.clearAllMocks()
  })

  it('collects only ready attachments with download_path', () => {
    const paths = collectReadyAttachmentPaths([
      {
        attachments: [
          { status: 'ready', download_path: '/a/1' },
          { status: 'pending', download_path: '/a/2' },
          { status: 'ready', download_path: '' },
        ],
      },
      {
        attachments: [{ status: 'ready', download_path: '/a/1' }],
      },
    ])
    expect(paths).toEqual(['/a/1'])
  })

  it('prefetches uncached paths without throwing', async () => {
    prefetchAttachmentBlobUrls(['/files/1', '/files/2'])
    await Promise.resolve()
    await Promise.resolve()
  })
})

describe('attachment blob cache eviction', () => {
  const createObjectURL = vi.spyOn(URL, 'createObjectURL')
  const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL')

  beforeEach(() => {
    createObjectURL.mockImplementation((blob) => `blob:${(blob as Blob).size}`)
    setAttachmentBlobCacheLimitsForTests(3, 1024)
  })

  afterEach(() => {
    clearAttachmentBlobCache()
    vi.clearAllMocks()
  })

  it('evicts LRU entry when max entries exceeded', async () => {
    await fetchAttachmentBlob('/files/10')
    await fetchAttachmentBlob('/files/20')
    await fetchAttachmentBlob('/files/30')
    expect(peekAttachmentBlobUrl('/files/10')).toBe('blob:10')
    expect(peekAttachmentBlobUrl('/files/20')).toBe('blob:20')
    expect(peekAttachmentBlobUrl('/files/30')).toBe('blob:30')

    await fetchAttachmentBlob('/files/40')
    expect(peekAttachmentBlobUrl('/files/10')).toBeNull()
    expect(peekAttachmentBlobUrl('/files/20')).toBe('blob:20')
    expect(peekAttachmentBlobUrl('/files/30')).toBe('blob:30')
    expect(peekAttachmentBlobUrl('/files/40')).toBe('blob:40')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:10')
  })

  it('evicts LRU entry when max bytes exceeded', async () => {
    setAttachmentBlobCacheLimitsForTests(10, 50)
    await fetchAttachmentBlob('/files/20')
    await fetchAttachmentBlob('/files/25')
    expect(peekAttachmentBlobUrl('/files/20')).toBe('blob:20')
    expect(peekAttachmentBlobUrl('/files/25')).toBe('blob:25')

    await fetchAttachmentBlob('/files/10')
    expect(peekAttachmentBlobUrl('/files/20')).toBeNull()
    expect(peekAttachmentBlobUrl('/files/25')).toBe('blob:25')
    expect(peekAttachmentBlobUrl('/files/10')).toBe('blob:10')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:20')
  })

  it('moves entry to MRU on peek', async () => {
    await fetchAttachmentBlob('/files/10')
    await fetchAttachmentBlob('/files/20')
    await fetchAttachmentBlob('/files/30')

    expect(peekAttachmentBlobUrl('/files/10')).toBe('blob:10')

    await fetchAttachmentBlob('/files/40')
    expect(peekAttachmentBlobUrl('/files/20')).toBeNull()
    expect(peekAttachmentBlobUrl('/files/10')).toBe('blob:10')
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:20')
  })

  it('moves entry to MRU on cache hit fetch', async () => {
    await fetchAttachmentBlob('/files/10')
    await fetchAttachmentBlob('/files/20')
    await fetchAttachmentBlob('/files/30')

    await fetchAttachmentBlob('/files/10')
    expect(http.get).toHaveBeenCalledTimes(3)

    await fetchAttachmentBlob('/files/40')
    expect(peekAttachmentBlobUrl('/files/20')).toBeNull()
    expect(peekAttachmentBlobUrl('/files/10')).toBe('blob:10')
  })
})
