import type { BotListResponse } from '@/entities/bot/types'
import { http } from '@/shared/api/http'

export async function listBots(): Promise<BotListResponse> {
  const { data } = await http.get<BotListResponse>('/bots')
  return data
}
