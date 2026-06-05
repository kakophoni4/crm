import type { ChatListItem } from '@/entities/chat/types'
import type { Contact } from '@/entities/contact/types'

export type GlobalSearchType = 'contacts' | 'messages' | 'chats'

export interface GlobalSearchMessageItem {
  chat_id: number
  contact_id: number
  message_id: number
  snippet: string
  matched_at: string
  lead_id?: number | null
  card_owner_user_id?: number | null
}

export interface SearchResultSection<T> {
  items: T[]
  next_cursor: string | null
}

export interface GlobalSearchResponse {
  contacts: SearchResultSection<Contact>
  messages: SearchResultSection<GlobalSearchMessageItem>
  chats: SearchResultSection<ChatListItem>
}

export interface GlobalSearchParams {
  q: string
  types?: GlobalSearchType[]
  limit_per_type?: number
  contacts_cursor?: string
  messages_cursor?: string
  chats_cursor?: string
}

export type GlobalSearchTab = GlobalSearchType
