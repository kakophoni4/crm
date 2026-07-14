import { http } from '@/shared/api/http'

export interface TelegramLink {
  id: number
  telegram_user_id: number
  telegram_username: string | null
  created_at: string
}

export interface NotificationSettings {
  group_senior_timeout_minutes: number
  mute_phrases: string[]
  telegram_links: TelegramLink[]
  bot_username: string | null
  bot_enabled: boolean
  can_link_multiple: boolean
  can_view_history: boolean
  can_manage_bot: boolean
  can_manage_escalation: boolean
}

export interface EscalationPolicy {
  scope: 'org' | 'department' | 'group' | string
  timeout_minutes: number
  mute_phrases: string[]
  effective_timeout_minutes: number
  effective_mute_phrases: string[]
  effective_source_scope: string | null
  updated_at: string | null
  updated_by_name: string | null
  default_timeout_minutes: number
}

export interface EscalationPolicyPatch {
  timeout_minutes: number
  mute_phrases: string[]
}

export interface NotificationBotAdmin {
  is_enabled: boolean
  bot_username: string | null
  has_token: boolean
  updated_at: string | null
  webhook_hint: string
}

export interface StaffNotificationEvent {
  id: number
  kind: string
  status: string
  contact_id: number | null
  chat_id: number | null
  group_id: number | null
  department_id: number | null
  target_user_id: number | null
  target_user_name: string | null
  telegram_user_id: number | null
  contact_name: string | null
  body_text: string | null
  created_at: string
  acked_at: string | null
  cancelled_at: string | null
}

export async function getNotificationSettings(): Promise<NotificationSettings> {
  const { data } = await http.get<NotificationSettings>('/notifications/me')
  return data
}

export async function linkTelegram(telegramUserId: number): Promise<TelegramLink> {
  const { data } = await http.post<TelegramLink>('/notifications/me/telegram-links', {
    telegram_user_id: telegramUserId,
  })
  return data
}

export async function unlinkTelegram(linkId: number): Promise<void> {
  await http.delete(`/notifications/me/telegram-links/${linkId}`)
}

export async function getEscalationPolicy(): Promise<EscalationPolicy> {
  const { data } = await http.get<EscalationPolicy>('/notifications/escalation-policy')
  return data
}

export async function patchEscalationPolicy(
  body: EscalationPolicyPatch,
): Promise<EscalationPolicy> {
  const { data } = await http.patch<EscalationPolicy>('/notifications/escalation-policy', body)
  return data
}

export async function getNotificationBot(): Promise<NotificationBotAdmin> {
  const { data } = await http.get<NotificationBotAdmin>('/notifications/bot')
  return data
}

export async function patchNotificationBot(body: {
  bot_token?: string
  is_enabled?: boolean
}): Promise<NotificationBotAdmin> {
  const { data } = await http.patch<NotificationBotAdmin>('/notifications/bot', body)
  return data
}

export async function syncNotificationBotWebhook(): Promise<NotificationBotAdmin> {
  const { data } = await http.post<NotificationBotAdmin>('/notifications/bot/sync-webhook')
  return data
}

export async function getNotificationHistory(params?: {
  cursor?: number
  limit?: number
  status?: string
}): Promise<{ items: StaffNotificationEvent[]; next_cursor: number | null }> {
  const { data } = await http.get<{ items: StaffNotificationEvent[]; next_cursor: number | null }>(
    '/notifications/history',
    { params },
  )
  return data
}
