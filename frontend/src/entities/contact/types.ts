/** Contact domain types — sync with OpenAPI via `npm run gen:api` when backend is up. */

import type { SelectOption } from 'naive-ui'



export type ContactStatus = 'new' | 'active' | 'returning' | 'disabled' | 'merged' | 'archived'



export type ReassignStrategy = 'first_responder' | 'random_available'



export interface GroupOwnershipItem {

  group_id: number

  group_name: string

  owner_user_id: number | null

  owner_full_name: string | null

  pending_inbound_at: string | null

  escalated_at: string | null

}



export interface ContactBotLink {

  bot_id: number

  bot_code: string

  bot_name: string

  chat_id: number

  chat_status: 'open' | 'in_progress' | 'closed' | 'archived'

}



export interface ContactWorkspace {

  chat_id: number

  lead_id: number

  group_id: number

  created_chat: boolean

  created_lead: boolean

}



export interface Contact {

  id: number

  full_name: string

  note?: string | null

  phone: string | null

  email: string | null

  telegram_username: string | null

  telegram_user_id?: number | null

  status: ContactStatus

  custom_fields: Record<string, unknown>

  assigned_department_id: number | null

  source: string | null

  archived_at: string | null

  created_by: number

  created_at: string

  updated_at: string

  group_ownership?: GroupOwnershipItem[]

  linked_bots?: ContactBotLink[]

  crm_summary?: ContactCrmSummary

  workspace?: ContactWorkspace

}

export interface ContactCrmSummary {
  prior_leads_count: number
  first_registered_at: string
}



export interface ContactListResponse {
  items: Contact[]
  next_cursor: string | null
  total: number
}

export interface ContactListParams {
  q?: string
  status?: ContactStatus
  cursor?: string
  offset?: number
  limit?: number
  custom_field_filters?: Record<string, string>
}



export interface ContactCreateBody {

  full_name: string

  phone?: string | null

  email?: string | null

  telegram_username?: string | null

  status?: ContactStatus

  custom_fields?: Record<string, unknown>

  assigned_department_id?: number | null

  source?: string | null

  open_workspace?: boolean

  workspace_group_id?: number | null

}



export interface ContactUpdateBody {

  full_name?: string

  note?: string | null

  phone?: string | null

  email?: string | null

  telegram_username?: string | null

  status?: ContactStatus

  custom_fields?: Record<string, unknown>

}



export interface FieldChange {

  id: number

  contact_id: number

  field_name: string

  old_value: unknown

  new_value: unknown

  changed_by: number

  changed_at: string

  changer_full_name: string | null

}



export interface FieldHistoryResponse {

  items: FieldChange[]

}



export interface ContactActivityItem {

  id: string

  label: string

  occurred_at: string

  actor_name?: string | null

}



export interface ContactActivityResponse {

  items: ContactActivityItem[]

}



export interface AuditEntry {

  id: number

  actor_id: number | null

  action: string

  entity_type: string

  entity_id: number

  payload: Record<string, unknown>

  request_id: string | null

  created_at: string

}



export interface ContactAuditResponse {

  items: AuditEntry[]

}



export interface ContactTransferRequestBody {

  to_user_id: number

  target_group_id?: number

  comment?: string

  force?: boolean

}



export interface ContactTransferRecord {

  id: number

  contact_id: number

  group_id: number

  from_user_id: number

  to_user_id: number

  requested_by: number

  state: ContactTransferState

  senior_user_id: number | null

  senior_decided_at: string | null

  recipient_decided_at: string | null

  force_assigned: boolean

  comment: string | null

  expires_at: string

  version: number

  updated_at: string

  created_at: string

  contact_name?: string | null

  group_name?: string | null

  from_user_name?: string | null

  to_user_name?: string | null

  requested_by_name?: string | null

}



export type ContactTransferState =

  | 'pending_senior'

  | 'pending_recipient'

  | 'accepted'

  | 'declined_senior'

  | 'declined_recipient'

  | 'cancelled'

  | 'expired'

  | 'pending'

  | 'approved'



export interface ContactTransferListResponse {

  items: ContactTransferRecord[]

}



export interface ReplyAuditItem {

  message_id: number

  chat_id: number

  author_user_id: number

  author_username?: string | null

  author_full_name: string

  card_owner_user_id: number

  card_owner_full_name: string

  is_on_behalf: boolean

  created_at: string

}



export interface ReplyAuditListResponse {

  items: ReplyAuditItem[]

}



export interface EscalationSettings {

  group_id: number

  first_response_timeout_minutes: number

  new_contact_reassign_strategy: ReassignStrategy

  notify_owner_on_inbound: boolean

  notify_group_on_escalation: boolean

  updated_at: string

}



export interface EscalationSettingsPatch {

  first_response_timeout_minutes?: number

  new_contact_reassign_strategy?: ReassignStrategy

  notify_owner_on_inbound?: boolean

  notify_group_on_escalation?: boolean

}



export type WorkingHoursSchedule = Record<string, string[][]>



export interface AfterHoursSettings {

  group_id: number

  enabled: boolean

  reply_text: string

  delay_minutes: number

  timezone: string

  working_hours: WorkingHoursSchedule

  cooldown_minutes: number

  updated_at: string

}



export interface AfterHoursSettingsPatch {

  enabled?: boolean

  reply_text?: string

  delay_minutes?: number

  timezone?: string

  working_hours?: WorkingHoursSchedule

  cooldown_minutes?: number

}



/** Актуальные статусы клиента (автоматика + неликвидный). */
export const CONTACT_CLIENT_STATUS_OPTIONS = [
  { label: 'Новый', value: 'new' as const },
  { label: 'Активный', value: 'active' as const },
  { label: 'Повторный', value: 'returning' as const },
  { label: 'Неликвидный', value: 'disabled' as const },
] as const

/** Фильтр на странице списка контактов. */
export const CONTACT_STATUS_FILTER_OPTIONS = [
  { label: 'Все статусы', value: null },
  ...CONTACT_CLIENT_STATUS_OPTIONS,
] as SelectOption[]

/** Единственный статус, который можно выставить вручную в карточке контакта. */
export const CONTACT_MANUAL_STATUS_OPTIONS = [
  { label: 'Неликвидный', value: 'disabled' as const },
]

const CONTACT_STATUS_LABEL_BY_CODE: Record<ContactStatus, string> = {
  new: 'Новый',
  active: 'Активный',
  returning: 'Повторный',
  disabled: 'Неликвидный',
  merged: 'Объединён',
  archived: 'В архиве',
}

export function contactStatusLabel(status: ContactStatus): string {
  return CONTACT_STATUS_LABEL_BY_CODE[status] ?? status
}



export const REASSIGN_STRATEGY_OPTIONS: { label: string; value: ReassignStrategy }[] = [

  { label: 'Первый ответивший', value: 'first_responder' },

  { label: 'Случайный доступный', value: 'random_available' },

]
