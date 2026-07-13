import { storage } from '@/shared/lib/storage'

/** Read JSON from localStorage. Returns null on miss / parse error. */
export function readJson<T>(key: string): T | null {
  const raw = storage.get(key)
  if (raw == null || raw === '') return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

/** Write JSON to localStorage. Silently ignores quota / private-mode failures. */
export function writeJson(key: string, value: unknown): boolean {
  try {
    storage.set(key, JSON.stringify(value))
    return true
  } catch {
    return false
  }
}

export function removeJson(key: string): void {
  storage.remove(key)
}

/** Debounce disk writes so rapid UI updates don't thrash localStorage. */
export function createDebouncedWriter(delayMs = 400): {
  schedule: (key: string, value: unknown) => void
  flush: () => void
  clear: () => void
} {
  const pending = new Map<string, unknown>()
  let timer: ReturnType<typeof setTimeout> | null = null

  const flush = (): void => {
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
    for (const [key, value] of pending) {
      writeJson(key, value)
    }
    pending.clear()
  }

  const schedule = (key: string, value: unknown): void => {
    pending.set(key, value)
    if (timer != null) clearTimeout(timer)
    timer = setTimeout(flush, delayMs)
  }

  const clear = (): void => {
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
    pending.clear()
  }

  return { schedule, flush, clear }
}
