import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  clearAttachmentBlobCache,
  collectReadyAttachmentPaths,
  prefetchAttachmentBlobUrls,
} from '@/shared/lib/attachment-blob-cache'

vi.mock('@/shared/api/http', () => ({
  http: {
    get: vi.fn(() =>
      Promise.resolve({ data: new Blob(['x'], { type: 'image/png' }) }),
    ),
  },
}))

describe('attachment blob cache prefetch', () => {
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
