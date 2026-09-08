/**
 * Простейший in-memory stale-while-revalidate кэш для страниц.
 *
 * Идея: при заходе на страницу мгновенно показываем последнее известное значение
 * (`peekCached`), а сеть дёргаем только если данные старше порога (`getCached`).
 * Это убирает "пустой экран + спиннер на 10-20 секунд" при каждой навигации.
 */

interface CacheEntry<T> {
  value: T
  at: number
}

const store = new Map<string, CacheEntry<unknown>>()
const MAX_ENTRIES = 100
const MAX_STALE_MS = 10 * 60 * 1000

/** Вернуть значение, только если оно свежее (моложе maxAgeMs). */
export function getCached<T>(key: string, maxAgeMs: number): T | undefined {
  const entry = store.get(key) as CacheEntry<T> | undefined
  if (!entry) return undefined
  if (Date.now() - entry.at > maxAgeMs) return undefined
  return entry.value
}

/** Вернуть последнее значение не старше 10 минут для мгновенного показа. */
export function peekCached<T>(key: string): T | undefined {
  const entry = store.get(key) as CacheEntry<T> | undefined
  if (entry && Date.now() - entry.at > MAX_STALE_MS) {
    store.delete(key)
    return undefined
  }
  return entry?.value
}

export function setCached<T>(key: string, value: T): void {
  store.delete(key)
  store.set(key, { value, at: Date.now() })
  while (store.size > MAX_ENTRIES) {
    const oldest = store.keys().next().value
    if (oldest == null) break
    store.delete(oldest)
  }
}

export function invalidateCached(key: string): void {
  store.delete(key)
}

/** Инвалидировать все ключи с указанным префиксом (например 'contacts:'). */
export function invalidateCachedPrefix(prefix: string): void {
  for (const key of store.keys()) {
    if (key.startsWith(prefix)) store.delete(key)
  }
}
