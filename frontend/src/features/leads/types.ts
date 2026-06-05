/** Lead domain types — aligned with L8-3 API (`/contacts/{id}/leads`, `/leads/{id}`). */

export interface LeadCommentItem {
  id: number
  body: string
  created_at: string
}

export interface LeadListItem {
  id: number
  contact_id: number
  group_id: number
  bot_id: number | null
  chat_id: number | null
  status_id: number | null
  status_code: string | null
  status_label: string | null
  bot_name: string | null
  bot_code: string | null
  title: string | null
  comment?: string | null
  comments?: LeadCommentItem[]
  closed_at: string | null
  created_at: string
  custom_fields?: Record<string, unknown> | null
}

export interface LeadDetail extends LeadListItem {
  updated_at: string
}

export interface LeadListResponse {
  items: LeadListItem[]
  next_cursor: string | null
}

export interface LeadPatchBody {
  status_id?: number
  title?: string
  comment?: string | null
}

export interface LeadListParams {
  group_id?: number
  status_id?: number
  open_only?: boolean
  cursor?: string
  limit?: number
}

export interface ContactCrmSummary {
  prior_leads_count: number
  first_registered_at: string
}

export interface PipelineStatusCount {
  status_id: number
  code: string
  label: string
  count: number
}

export interface OperatorDashboardKpi {
  user_id: number
  display_name: string
  chats_today_count: number
  avg_response_minutes: number | null
  closed_won_today_count: number
  closed_lost_today_count: number
  open_leads_count: number
}

export interface CrmDashboardSummary {
  chats_today_count: number
  avg_response_minutes: number | null
  closed_leads_today_count: number
  closed_won_today_count: number
  closed_lost_today_count: number
  new_clients_today_count: number
  open_leads_count: number
  closed_today_count: number
  by_pipeline_status: PipelineStatusCount[]
  by_operator: OperatorDashboardKpi[]
}

export type { ChatLabelSnippet, CurrentLeadSnippet } from '@/entities/chat/types'

export type StatusKind = 'chat_label' | 'lead_pipeline'

export interface StatusOption {
  id: number
  code: string
  kind?: StatusKind
  label: string
  color: string | null
  sort_order: number
  is_active: boolean
}

export interface StatusListResponse {
  items: StatusOption[]
}
