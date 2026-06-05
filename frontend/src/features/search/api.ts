import type { GlobalSearchParams, GlobalSearchResponse } from '@/features/search/types'
import { http } from '@/shared/api/http'

function buildSearchParams(params: GlobalSearchParams): Record<string, string | number> {
  const query: Record<string, string | number> = { q: params.q }
  if (params.types?.length) query.types = params.types.join(',')
  if (params.limit_per_type != null) query.limit_per_type = params.limit_per_type
  if (params.contacts_cursor) query.contacts_cursor = params.contacts_cursor
  if (params.messages_cursor) query.messages_cursor = params.messages_cursor
  if (params.chats_cursor) query.chats_cursor = params.chats_cursor
  return query
}

export async function globalSearch(params: GlobalSearchParams): Promise<GlobalSearchResponse> {
  const { data } = await http.get<GlobalSearchResponse>('/search', {
    params: buildSearchParams(params),
  })
  return data
}
