import type {
  ChatDetail,
  ChatListParams,
  ChatListResponse,
  MessageListResponse,
  SendMessageBody,
} from '@/entities/chat/types'
import type { ChatMessage } from '@/entities/chat/types'
import { http } from '@/shared/api/http'

function buildListParams(params: ChatListParams): Record<string, string | number | boolean> {
  const query: Record<string, string | number | boolean> = {}
  if (params.status) query.status = params.status
  if (params.status_id != null) query.status_id = params.status_id
  if (params.assigned_user_id != null) query.assigned_user_id = params.assigned_user_id
  if (params.contact_id != null) query.contact_id = params.contact_id
  if (params.bot_id != null) query.bot_id = params.bot_id
  if (params.unread_only) query.unread_only = true
  if (params.needs_reply) query.needs_reply = true
  if (params.card_owner_user_id != null) query.card_owner_user_id = params.card_owner_user_id
  if (params.assigned_group_id != null) query.assigned_group_id = params.assigned_group_id
  if (params.q) query.q = params.q
  if (params.sort) query.sort = params.sort
  if (params.cursor) query.cursor = params.cursor
  if (params.limit) query.limit = params.limit
  if (params.lead_status_id != null) query.lead_status_id = params.lead_status_id
  if (params.lead_open_only) query.lead_open_only = true
  return query
}

export async function patchChatStatusId(chatId: number, statusId: number): Promise<ChatDetail> {
  const { data } = await http.patch<ChatDetail>(`/chats/${chatId}/status_id`, {
    status_id: statusId,
  })
  return data
}

let listChatsAbort: AbortController | null = null

export async function listChats(params: ChatListParams = {}): Promise<ChatListResponse> {
  listChatsAbort?.abort()
  listChatsAbort = new AbortController()
  const signal = listChatsAbort.signal
  const { data } = await http.get<ChatListResponse>('/chats', {
    params: buildListParams(params),
    signal,
  })
  return data
}

export async function markChatRead(
  chatId: number,
  body: { last_read_message_id?: number } = {},
): Promise<void> {
  await http.post(`/chats/${chatId}/read`, body)
}

export async function getChat(id: number): Promise<ChatDetail> {
  const { data } = await http.get<ChatDetail>(`/chats/${id}`)
  return data
}

export async function listMessages(
  chatId: number,
  params: { cursor?: string; limit?: number; lead_id?: number } = {},
): Promise<MessageListResponse> {
  const query: Record<string, string | number> = {}
  if (params.cursor) query.cursor = params.cursor
  if (params.limit) query.limit = params.limit
  if (params.lead_id != null) query.lead_id = params.lead_id
  const { data } = await http.get<MessageListResponse>(`/chats/${chatId}/messages`, {
    params: query,
  })
  return data
}

export async function sendMessage(
  chatId: number,
  body: SendMessageBody,
): Promise<ChatMessage> {
  const { data } = await http.post<ChatMessage>(`/chats/${chatId}/messages`, body)
  return data
}

export async function startTakeover(chatId: number, reason?: string): Promise<unknown> {
  const { data } = await http.post(`/chats/${chatId}/takeover`, { reason: reason ?? null })
  return data
}

export async function releaseTakeover(chatId: number): Promise<unknown> {
  const { data } = await http.post(`/chats/${chatId}/takeover/release`)
  return data
}

export async function uploadFile(
  file: File,
): Promise<{ id: number; name?: string; mime?: string; size?: number }> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<{ id: number; name?: string; mime?: string; size?: number }>(
    '/files',
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120_000,
    },
  )
  return data
}
