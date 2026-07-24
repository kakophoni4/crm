import { listGroups } from '@/features/admin/api'

const TTL_MS = 5 * 60 * 1000

let cachedAt = 0
let groupsById = new Map<number, string>()
let loadPromise: Promise<void> | null = null

async function refreshGroupDirectory(): Promise<void> {
  const items = await listGroups()
  const next = new Map<number, string>()
  for (const group of items) {
    next.set(group.id, group.name)
  }
  groupsById = next
  cachedAt = Date.now()
}

export async function ensureGroupDirectory(): Promise<void> {
  if (Date.now() - cachedAt < TTL_MS && groupsById.size > 0) {
    return
  }
  if (loadPromise) {
    await loadPromise
    return
  }
  loadPromise = refreshGroupDirectory()
  try {
    await loadPromise
  } catch {
    // Keep last successful directory; callers must not hang the whole chats UI.
  } finally {
    loadPromise = null
  }
}

export function lookupGroupName(groupId: number | null | undefined): string | null {
  if (groupId == null) return null
  return groupsById.get(groupId) ?? null
}

export function resetGroupDirectoryCacheForTests(): void {
  cachedAt = 0
  groupsById = new Map()
  loadPromise = null
}
