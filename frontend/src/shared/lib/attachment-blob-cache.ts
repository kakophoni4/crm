import { http } from '@/shared/api/http'

export interface CachedAttachmentBlob {
  url: string
  mime: string
  blob: Blob
}

export type AttachmentDownloadPriority = 'high' | 'normal'

export interface ReadyAttachmentRef {
  path: string
  mime: string | null
}

const cache = new Map<string, CachedAttachmentBlob>()
const inflight = new Map<string, Promise<CachedAttachmentBlob>>()

/** Parallel attachment warm-up; keep below browser per-host connection budget. */
const MAX_CONCURRENT_DOWNLOADS = 4
const QUEUE_WAIT_MS = 120_000
const DOWNLOAD_MS = 120_000

let activeDownloads = 0
const highWaitQueue: Array<() => void> = []
const normalWaitQueue: Array<() => void> = []

function acquireDownloadSlot(
  deadlineMs: number,
  priority: AttachmentDownloadPriority,
): Promise<void> {
  if (activeDownloads < MAX_CONCURRENT_DOWNLOADS) {
    activeDownloads += 1
    return Promise.resolve()
  }
  const waitQueue = priority === 'high' ? highWaitQueue : normalWaitQueue
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
  const next = highWaitQueue.shift() ?? normalWaitQueue.shift()
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
  priority: AttachmentDownloadPriority = 'high',
): Promise<CachedAttachmentBlob> {
  const cached = cache.get(downloadPath)
  if (cached) return cached

  const pending = inflight.get(downloadPath)
  if (pending) return pending

  const task = (async () => {
    const deadlineMs = Date.now() + QUEUE_WAIT_MS + DOWNLOAD_MS
    await acquireDownloadSlot(deadlineMs, priority)
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
  priority: AttachmentDownloadPriority = 'high',
): Promise<string> {
  const entry = await fetchAttachmentBlob(downloadPath, mimeHint, priority)
  return entry.url
}

export function collectReadyAttachmentPaths(
  messages: Iterable<{ attachments?: Record<string, unknown>[] }>,
): string[] {
  return collectReadyAttachments(messages).map((item) => item.path)
}

export function collectReadyAttachments(
  messages: Iterable<{ attachments?: Record<string, unknown>[] }>,
): ReadyAttachmentRef[] {
  const byPath = new Map<string, ReadyAttachmentRef>()
  for (const msg of messages) {
    for (const att of msg.attachments ?? []) {
      if (String(att.status ?? '') !== 'ready') continue
      const path = att.download_path
      if (typeof path !== 'string' || path.length === 0) continue
      const mimeRaw = att.mime
      byPath.set(path, {
        path,
        mime: typeof mimeRaw === 'string' && mimeRaw.length > 0 ? mimeRaw : null,
      })
    }
  }
  return [...byPath.values()]
}

/** Best-effort warm-up; skips paths already cached or in flight. */
export function prefetchAttachmentBlobUrls(
  downloadPaths: Iterable<string>,
  options: { priority?: AttachmentDownloadPriority } = {},
): void {
  const priority = options.priority ?? 'normal'
  for (const path of downloadPaths) {
    if (peekAttachmentBlobUrl(path) || inflight.has(path)) continue
    void fetchAttachmentBlobUrl(path, null, priority).catch(() => undefined)
  }
}

function isLightPreviewMime(mime: string | null): boolean {
  if (!mime) return false
  return mime.startsWith('image/') || mime.startsWith('audio/') || mime === 'application/pdf'
}

export function prefetchAttachmentsForMessages(
  messages: Iterable<{ attachments?: Record<string, unknown>[] }>,
  options: { priority?: AttachmentDownloadPriority; limit?: number } = {},
): void {
  const priority = options.priority ?? 'normal'
  // Background warm-up: only light previews, capped — heavy docs starve open-chat traffic.
  const limit = options.limit ?? (priority === 'high' ? 24 : 6)
  let queued = 0
  for (const { path, mime } of collectReadyAttachments(messages)) {
    if (queued >= limit) break
    if (priority !== 'high' && !isLightPreviewMime(mime)) continue
    if (peekAttachmentBlobUrl(path) || inflight.has(path)) continue
    queued += 1
    void fetchAttachmentBlob(path, mime, priority).catch(() => undefined)
  }
}

/** Jump the queue — open chat, hover, top list chats. */
export function priorityPrefetchAttachmentsForMessages(
  messages: Iterable<{ attachments?: Record<string, unknown>[] }>,
): void {
  prefetchAttachmentsForMessages(messages, { priority: 'high' })
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
  highWaitQueue.length = 0
  normalWaitQueue.length = 0
}
