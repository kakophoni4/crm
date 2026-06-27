import { http } from '@/shared/api/http'

export interface CachedAttachmentBlob {
  url: string
  mime: string
  blob: Blob
}

const cache = new Map<string, CachedAttachmentBlob>()
const inflight = new Map<string, Promise<CachedAttachmentBlob>>()

/** Keep below browser per-host connection limit so API calls are not starved. */
const MAX_CONCURRENT_DOWNLOADS = 4
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
  return cache.get(downloadPath)?.url ?? null
}

export function peekAttachmentBlob(downloadPath: string): CachedAttachmentBlob | null {
  return cache.get(downloadPath) ?? null
}

function normalizeBlob(raw: Blob, mimeHint: string | null | undefined, headerMime: string | undefined): Blob {
  const fromHeader = headerMime?.split(';')[0]?.trim()
  const mime =
    (fromHeader && fromHeader !== 'application/octet-stream' ? fromHeader : null) ||
    (mimeHint && mimeHint !== 'application/octet-stream' ? mimeHint : null) ||
    (raw.type && raw.type !== 'application/octet-stream' ? raw.type : null) ||
    'application/octet-stream'
  if (raw.type === mime) return raw
  return new Blob([raw], { type: mime })
}

export async function fetchAttachmentBlob(
  downloadPath: string,
  mimeHint?: string | null,
): Promise<CachedAttachmentBlob> {
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
      const blob = normalizeBlob(
        resp.data as Blob,
        mimeHint,
        resp.headers['content-type'] as string | undefined,
      )
      const url = URL.createObjectURL(blob)
      const entry: CachedAttachmentBlob = { url, mime: blob.type, blob }
      cache.set(downloadPath, entry)
      return entry
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

export async function fetchAttachmentBlobUrl(
  downloadPath: string,
  mimeHint?: string | null,
): Promise<string> {
  const entry = await fetchAttachmentBlob(downloadPath, mimeHint)
  return entry.url
}

export function collectReadyAttachmentPaths(
  messages: Iterable<{ attachments?: Record<string, unknown>[] }>,
): string[] {
  const paths = new Set<string>()
  for (const msg of messages) {
    for (const att of msg.attachments ?? []) {
      if (String(att.status ?? '') !== 'ready') continue
      const path = att.download_path
      if (typeof path === 'string' && path.length > 0) {
        paths.add(path)
      }
    }
  }
  return [...paths]
}

/** Best-effort warm-up; skips paths already cached or in flight. */
export function prefetchAttachmentBlobUrls(downloadPaths: Iterable<string>): void {
  for (const path of downloadPaths) {
    if (peekAttachmentBlobUrl(path) || inflight.has(path)) continue
    void fetchAttachmentBlobUrl(path).catch(() => undefined)
  }
}

export function prefetchAttachmentsForMessages(
  messages: Iterable<{ attachments?: Record<string, unknown>[] }>,
): void {
  prefetchAttachmentBlobUrls(collectReadyAttachmentPaths(messages))
}

export function releaseAttachmentBlobUrl(downloadPath: string): void {
  const entry = cache.get(downloadPath)
  if (!entry) return
  URL.revokeObjectURL(entry.url)
  cache.delete(downloadPath)
  inflight.delete(downloadPath)
}

/** Test helper */
export function clearAttachmentBlobCache(): void {
  for (const entry of cache.values()) {
    URL.revokeObjectURL(entry.url)
  }
  cache.clear()
  inflight.clear()
  activeDownloads = 0
  waitQueue.length = 0
}
