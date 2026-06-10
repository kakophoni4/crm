export type ChatStatusCode = 'open' | 'in_progress' | 'closed' | 'archived'

export interface CurrentLeadSnippet {
  id: number
  status_id: number
  label: string
  comment?: string | null
  closed_at: string | null
}

export interface ChatLabelSnippet {
  status_id: number | null
  code: string | null
  label: string | null
}

export interface ChatListItem {
  id: number
  contact_id: number
  contact_name: string
  bot_id: number | null
  assigned_user_id: number | null
  assigned_group_id: number | null
  assigned_group_name?: string | null
  assigned_department_id: number | null
  status: ChatStatusCode
  status_id: number | null
  last_message_at: string | null
  last_message_preview: string | null
  /** Per-operator unread (chat_read_state vs latest message). */
  unread_for_me?: boolean
  /** Card owner in the chat's group (ownership model). */
  card_owner_user_id?: number | null
  card_owner_full_name?: string | null
  /** Group scope for ownership / transfer (inbox group when chat has no assigned_group_id). */
  card_owner_group_id?: number | null
  pending_inbound_at?: string | null
  escalated_at?: string | null
  needs_response?: boolean
  needs_reply?: boolean
  chat_label?: ChatLabelSnippet | null
  contact_client_label?: string | null
  current_lead?: CurrentLeadSnippet | null
}

export type ChatDetail = ChatListItem

export interface ChatListResponse {
  items: ChatListItem[]
  next_cursor: string | null
}

export type ChatListSort = 'last_message_at_desc' | 'created_at_desc' | 'unread_first'

export interface ChatListParams {
  status?: ChatStatusCode
  status_id?: number
  assigned_user_id?: number
  contact_id?: number
  bot_id?: number
  unread_only?: boolean
  needs_reply?: boolean
  card_owner_user_id?: number
  assigned_group_id?: number
  q?: string
  sort?: ChatListSort
  cursor?: string
  limit?: number
  lead_status_id?: number
  lead_open_only?: boolean
}

export type MessageDirection = 'inbound' | 'outbound'

export type MessageScope = 'current_lead' | 'all'

export interface ChatMessage {
  id: number
  chat_id: number
  lead_id?: number | null
  direction: MessageDirection
  kind: string
  text: string | null
  attachments: Record<string, unknown>[]
  sender_user_id: number | null
  reply_to_message_id: number | null
  created_at: string
  idempotency_key?: string | null
  is_on_behalf?: boolean
  author_full_name?: string | null
  card_owner_full_name?: string | null
  author_user_id?: number | null
  card_owner_user_id?: number | null
  /** Client-only optimistic row */
  _optimistic?: boolean
  _failed?: boolean
  _clientKey?: string
}

export type ChatListTab = 'mine' | 'group' | 'needs_response'

export interface MessageListResponse {
  items: ChatMessage[]
  next_cursor: string | null
}

export interface SendMessageBody {
  text?: string
  attachments?: { file_id?: number; name?: string; mime?: string; size?: number; url?: string }[]
  idempotency_key?: string
}

export interface TakeoverState {
  chat_id: number
  senior_user_id: number
  takeover_id?: number
}

export interface WsServerFrame {
  type: string
  topic?: string
  payload?: Record<string, unknown>
}

export const CHAT_STATUS_OPTIONS = [
  { label: 'Открыт', value: 'open' as const },
  { label: 'В работе', value: 'in_progress' as const },
  { label: 'Закрыт', value: 'closed' as const },
  { label: 'Архив', value: 'archived' as const },
]

export const CHAT_SORT_OPTIONS = [
  { label: 'По последнему сообщению', value: 'last_message_at_desc' as const },
  { label: 'По дате создания', value: 'created_at_desc' as const },
  { label: 'Сначала непрочитанные', value: 'unread_first' as const },
]
