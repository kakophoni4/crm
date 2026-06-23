import { http } from '@/shared/api/http'

const cache = new Map<string, string>()
const inflight = new Map<string, Promise<string>>()

/** Keep below browser per-host connection limit so API calls are not starved. */
const MAX_CONCURRENT_DOWNLOADS = 2
const QUEUE_WAIT_MS = 30_000
const DOWNLOAD_MS = 60_000

let activeDownloads = 0
const waitQueue: Array<() => void> = []

function acquireDownloadSlot(deadlineMs: number): Promise<void> {
  if (activeDownloads < MAX_CONCURRENT_DOWNLOADS) {
    activeDownloads += 1
    return Promise.resolve()
  }
  return new Promise((resolve, reject) => {
    const wait = (): void => {
      if (Date.now() >= deadlineMs) {
        reject(new Error('attachment_queue_timeout'))
        return
      }
      if (activeDownloads < MAX_CONCURRENT_DOWNLOADS) {
        activeDownloads += 1
        resolve()
        return
      }
      waitQueue.push(wait)
    }
    wait()
  })
}

function releaseDownloadSlot(): void {
  activeDownloads = Math.max(0, activeDownloads - 1)
  const next = waitQueue.shift()
  if (next) next()
}

export function peekAttachmentBlobUrl(downloadPath: string): string | null {
  return cache.get(downloadPath) ?? null
}

export async function fetchAttachmentBlobUrl(downloadPath: string): Promise<string> {
  const cached = cache.get(downloadPath)
  if (cached) return cached

  const pending = inflight.get(downloadPath)
  if (pending) return pending

  const task = (async () => {
    const deadlineMs = Date.now() + QUEUE_WAIT_MS + DOWNLOAD_MS
    await acquireDownloadSlot(deadlineMs)
    try {
      const remaining = deadlineMs - Date.now()
      if (remaining <= 0) {
        throw new Error('attachment_timeout')
      }
      const resp = await http.get(downloadPath, {
        responseType: 'blob',
        timeout: remaining,
      })
      const url = URL.createObjectURL(resp.data)
      cache.set(downloadPath, url)
      return url
    } finally {
      releaseDownloadSlot()
      inflight.delete(downloadPath)
    }
  })()

  inflight.set(downloadPath, task)
  return task.catch((err) => {
    inflight.delete(downloadPath)
    throw err
  })
}

export function releaseAttachmentBlobUrl(downloadPath: string): void {
  const url = cache.get(downloadPath)
  if (!url) return
  URL.revokeObjectURL(url)
  cache.delete(downloadPath)
  inflight.delete(downloadPath)
}

/** Test helper */
export function clearAttachmentBlobCache(): void {
  for (const url of cache.values()) {
    URL.revokeObjectURL(url)
  }
  cache.clear()
  inflight.clear()
  activeDownloads = 0
  waitQueue.length = 0
}
