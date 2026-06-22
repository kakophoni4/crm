export interface BotListItem {
  id: number
  code: string
  name: string
  channel?: 'telegram' | 'whatsapp'
  purpose: string | null
  owner_type: string
  owner_id: number
  is_active: boolean
  last_seen_at: string | null
}

export interface BotListResponse {
  items: BotListItem[]
}
