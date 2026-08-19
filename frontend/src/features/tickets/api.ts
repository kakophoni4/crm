import { http } from '@/shared/api/http'

import type {
  CompanyListResponse,
  SmertnikiCompany,
  SmertnikiTicket,
  TicketListResponse,
} from '@/features/tickets/types'

export async function listTicketCompanies(): Promise<CompanyListResponse> {
  const { data } = await http.get<CompanyListResponse>('/tickets/companies')
  return data
}

export async function addTicketCompanies(inns: string[], checkNew = true): Promise<unknown> {
  const { data } = await http.post('/tickets/companies/inns', { inns, check_new: checkNew }, {
    timeout: 180000,
  })
  return data
}

export async function patchTicketCompany(
  companyId: number,
  body: { inn?: string; is_active?: boolean; name?: string },
): Promise<SmertnikiCompany> {
  const { data } = await http.patch<SmertnikiCompany>(`/tickets/companies/${companyId}`, body)
  return data
}

export async function checkTicketCompany(companyId: number): Promise<unknown> {
  const { data } = await http.post(`/tickets/companies/${companyId}/check`, null, {
    timeout: 120000,
  })
  return data
}

export async function checkAllTicketCompanies(): Promise<unknown> {
  const { data } = await http.post('/tickets/companies/check-all', null, { timeout: 30000 })
  return data
}

export async function listSmertnikiTickets(params?: {
  issue_type?: string
  status?: string
}): Promise<TicketListResponse> {
  const { data } = await http.get<TicketListResponse>('/tickets', { params })
  return data
}

export async function createSmertnikiTicket(body: {
  company_id: number
  issue_type: string
  title: string
  details?: string | null
}): Promise<SmertnikiTicket> {
  const { data } = await http.post<SmertnikiTicket>('/tickets', body)
  return data
}

export async function healSmertnikiTicket(ticketId: number): Promise<SmertnikiTicket> {
  const { data } = await http.post<SmertnikiTicket>(`/tickets/${ticketId}/heal`)
  return data
}
