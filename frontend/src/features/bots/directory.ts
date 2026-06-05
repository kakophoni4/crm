import { listBots } from '@/features/bots/api'
import type { BotListItem } from '@/entities/bot/types'

const TTL_MS = 5 * 60 * 1000

let cachedAt = 0
let botsById = new Map<number, BotListItem>()
let loadPromise: Promise<void> | null = null

async function refreshBotDirectory(): Promise<void> {
  const data = await listBots()
  const next = new Map<number, BotListItem>()
  for (const bot of data.items) {
    next.set(bot.id, bot)
  }
  botsById = next
  cachedAt = Date.now()
}

export async function ensureBotDirectory(): Promise<void> {
  if (Date.now() - cachedAt < TTL_MS && botsById.size > 0) {
    return
  }
  if (loadPromise) {
    await loadPromise
    return
  }
  loadPromise = refreshBotDirectory()
  try {
    await loadPromise
  } finally {
    loadPromise = null
  }
}

export function lookupBotName(botId: number | null | undefined): string | null {
  if (botId == null) return null
  return botsById.get(botId)?.name ?? null
}

export function lookupBotCode(botId: number | null | undefined): string | null {
  if (botId == null) return null
  return botsById.get(botId)?.code ?? null
}

export function resetBotDirectoryCacheForTests(): void {
  cachedAt = 0
  botsById = new Map()
  loadPromise = null
}
