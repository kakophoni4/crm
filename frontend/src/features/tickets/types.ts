export type TicketIssueType = 'address' | 'director' | 'founder' | 'liquidation' | 'other'
export type TicketStatus = 'in_progress' | 'healed' | 'closed'

export interface SmertnikiCompany {
  id: number
  inn: string | null
  ogrn: string
  name: string | null
  short_name: string | null
  status_text: string | null
  unreliable_address: boolean
  unreliable_director: boolean
  unreliable_founder: boolean
  is_liquidating: boolean
  is_liquidated: boolean
  is_active: boolean
  last_checked_at: string | null
  last_error: string | null
  rusprofile_url: string | null
}

export interface SmertnikiTicket {
  id: number
  company_id: number
  company_name: string | null
  company_inn: string | null
  issue_type: TicketIssueType | string
  status: TicketStatus | string
  title: string
  details: string | null
  age_days: number
  created_at: string
  closed_at: string | null
}

export interface CompanyListResponse {
  items: SmertnikiCompany[]
}

export interface TicketListResponse {
  items: SmertnikiTicket[]
}

export const TICKET_TYPE_OPTIONS = [
  { label: 'Адрес', value: 'address' },
  { label: 'Должностное лицо', value: 'director' },
  { label: 'Учредитель', value: 'founder' },
  { label: 'Ликвидация', value: 'liquidation' },
  { label: 'Прочее', value: 'other' },
]

export const TICKET_STATUS_OPTIONS = [
  { label: 'В работе', value: 'in_progress' },
  { label: 'Вылечена', value: 'healed' },
  { label: 'Закрыта', value: 'closed' },
]

export function ticketTypeLabel(value: string): string {
  return TICKET_TYPE_OPTIONS.find((item) => item.value === value)?.label ?? value
}
