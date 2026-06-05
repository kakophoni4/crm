import { http } from '@/shared/api/http'

const cache = new Map<string, string>()
const inflight = new Map<string, Promise<string>>()

export function peekAttachmentBlobUrl(downloadPath: string): string | null {
  return cache.get(downloadPath) ?? null
}

export async function fetchAttachmentBlobUrl(downloadPath: string): Promise<string> {
  const cached = cache.get(downloadPath)
  if (cached) return cached

  const pending = inflight.get(downloadPath)
  if (pending) return pending

  const task = http
    .get(downloadPath, { responseType: 'blob', timeout: 120_000 })
    .then((resp) => {
      const url = URL.createObjectURL(resp.data)
      cache.set(downloadPath, url)
      inflight.delete(downloadPath)
      return url
    })
    .catch((err) => {
      inflight.delete(downloadPath)
      throw err
    })

  inflight.set(downloadPath, task)
  return task
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
}
