import { createHash, createHmac } from 'node:crypto'

import type { APIRequestContext } from '@playwright/test'

import { apiBaseUrl } from './env'

export interface AuthSession {
  accessToken: string
  userId: number
  fullName: string
  email: string
  role: string
}

export interface ChatListItem {
  id: number
  contact_id: number
  contact_name: string
  assigned_group_id: number | null
  card_owner_user_id?: number | null
  last_message_preview: string | null
}

export interface ContactDetail {
  id: number
  group_ownership: { group_id: number; owner_user_id: number | null }[]
}

export interface ReplyAuditItem {
  author_user_id: number
  card_owner_user_id: number
  is_on_behalf: boolean
}

export interface FieldHistoryItem {
  field_name: string
  old_value: unknown
  new_value: unknown
  changed_by: number
  changer_full_name: string | null
}

function bodySha256Hex(body: Buffer): string {
  return createHash('sha256').update(body).digest('hex')
}

export function signInbound(eventId: string, timestamp: string, body: Buffer, secret: string): string {
  const canonical = `${eventId}.${timestamp}.${bodySha256Hex(body)}`
  return createHmac('sha256', secret).update(canonical).digest('hex')
}

export async function loginApi(
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<AuthSession> {
  const response = await request.post(`${apiBaseUrl()}/auth/login`, {
    data: { email, password },
  })
  if (!response.ok()) {
    throw new Error(`login failed for ${email}: ${response.status()} ${await response.text()}`)
  }
  const data = (await response.json()) as {
    access_token: string
    user: { id: number; full_name: string; email: string; role: string }
  }
  return {
    accessToken: data.access_token,
    userId: data.user.id,
    fullName: data.user.full_name,
    email: data.user.email,
    role: data.user.role,
  }
}

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` }
}

export async function listChatsApi(
  request: APIRequestContext,
  token: string,
  params: Record<string, string | number | boolean> = {},
): Promise<ChatListItem[]> {
  const response = await request.get(`${apiBaseUrl()}/chats`, {
    headers: authHeaders(token),
    params,
  })
  if (!response.ok()) {
    throw new Error(`list chats failed: ${response.status()} ${await response.text()}`)
  }
  const data = (await response.json()) as { items: ChatListItem[] }
  return data.items
}

export async function getContactApi(
  request: APIRequestContext,
  token: string,
  contactId: number,
): Promise<ContactDetail> {
  const response = await request.get(`${apiBaseUrl()}/contacts/${contactId}`, {
    headers: authHeaders(token),
  })
  if (!response.ok()) {
    throw new Error(`get contact failed: ${response.status()} ${await response.text()}`)
  }
  return (await response.json()) as ContactDetail
}

export async function getReplyAuditApi(
  request: APIRequestContext,
  token: string,
  contactId: number,
  groupId: number,
): Promise<ReplyAuditItem[]> {
  const response = await request.get(
    `${apiBaseUrl()}/contacts/${contactId}/groups/${groupId}/reply-audit`,
    { headers: authHeaders(token) },
  )
  if (!response.ok()) {
    throw new Error(`reply-audit failed: ${response.status()} ${await response.text()}`)
  }
  const data = (await response.json()) as { items: ReplyAuditItem[] }
  return data.items
}

export async function getContactHistoryApi(
  request: APIRequestContext,
  token: string,
  contactId: number,
): Promise<FieldHistoryItem[]> {
  const response = await request.get(`${apiBaseUrl()}/contacts/${contactId}/history`, {
    headers: authHeaders(token),
    params: { limit: 50 },
  })
  if (!response.ok()) {
    throw new Error(`contact history failed: ${response.status()} ${await response.text()}`)
  }
  const data = (await response.json()) as { items: FieldHistoryItem[] }
  return data.items
}

export async function postBotEvent(
  request: APIRequestContext,
  options: {
    botCode: string
    secret: string
    telegramUserId: number
    text: string
    firstName?: string
    lastName?: string
  },
): Promise<{ eventId: string; status: number }> {
  const eventId = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  const envelope = {
    event: 'message.received',
    event_id: eventId,
    occurred_at: new Date().toISOString(),
    bot_code: options.botCode,
    payload: {
      contact: {
        telegram_user_id: options.telegramUserId,
        telegram_username: `e2e_${options.telegramUserId}`,
        first_name: options.firstName ?? 'E2E',
        last_name: options.lastName ?? 'Inbound',
      },
      message: {
        external_id: `ext_${eventId}`,
        text: options.text,
        attachments: [],
        sent_at: new Date().toISOString(),
      },
    },
  }
  const body = Buffer.from(JSON.stringify(envelope))
  const timestamp = String(Math.floor(Date.now() / 1000))
  const signature = signInbound(eventId, timestamp, body, options.secret)

  const response = await request.post(`${apiBaseUrl()}/bot-events`, {
    headers: {
      'X-Bot-Code': options.botCode,
      'X-Event-Id': eventId,
      'X-Timestamp': timestamp,
      'X-Signature': signature,
      'Content-Type': 'application/json',
    },
    data: body,
  })
  return { eventId, status: response.status() }
}

export async function startTakeoverApi(
  request: APIRequestContext,
  token: string,
  chatId: number,
): Promise<void> {
  const response = await request.post(`${apiBaseUrl()}/chats/${chatId}/takeover`, {
    headers: authHeaders(token),
    data: { reason: 'e2e takeover' },
  })
  if (!response.ok() && response.status() !== 409) {
    throw new Error(`takeover failed: ${response.status()} ${await response.text()}`)
  }
}

export async function sendMessageApi(
  request: APIRequestContext,
  token: string,
  chatId: number,
  text: string,
  idempotencyKey?: string,
): Promise<void> {
  const response = await request.post(`${apiBaseUrl()}/chats/${chatId}/messages`, {
    headers: authHeaders(token),
    data: {
      text,
      kind: 'text',
      idempotency_key: idempotencyKey ?? `e2e-${Date.now()}`,
    },
  })
  if (response.status() !== 202 && !response.ok()) {
    throw new Error(`send message failed: ${response.status()} ${await response.text()}`)
  }
}

export async function pollUntil<T>(
  fn: () => Promise<T | null | undefined>,
  options: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<T> {
  const timeoutMs = options.timeoutMs ?? 60_000
  const intervalMs = options.intervalMs ?? 1_000
  const deadline = Date.now() + timeoutMs
  let lastError: unknown
  while (Date.now() < deadline) {
    try {
      const value = await fn()
      if (value != null) return value
    } catch (err) {
      lastError = err
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  throw new Error(`pollUntil timed out after ${timeoutMs}ms${lastError ? `: ${lastError}` : ''}`)
}
