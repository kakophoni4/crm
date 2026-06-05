import type {
  CrmDashboardSummary,
  LeadDetail,
  LeadListParams,
  LeadListResponse,
  LeadPatchBody,
  StatusKind,
  StatusListResponse,
} from '@/features/leads/types'
import { http } from '@/shared/api/http'

function buildLeadListParams(params: LeadListParams): Record<string, string | number | boolean> {
  const query: Record<string, string | number | boolean> = {}
  if (params.group_id != null) query.group_id = params.group_id
  if (params.status_id != null) query.status_id = params.status_id
  if (params.open_only != null) query.open_only = params.open_only
  if (params.cursor) query.cursor = params.cursor
  if (params.limit) query.limit = params.limit
  return query
}

export async function getCrmDashboardSummary(): Promise<CrmDashboardSummary> {
  const { data } = await http.get<CrmDashboardSummary>('/crm-summary')
  return data
}

export async function listContactLeads(
  contactId: number,
  params: LeadListParams = {},
): Promise<LeadListResponse> {
  const { data } = await http.get<LeadListResponse>(`/contacts/${contactId}/leads`, {
    params: buildLeadListParams(params),
  })
  return data
}

export async function getLead(leadId: number): Promise<LeadDetail> {
  const { data } = await http.get<LeadDetail>(`/leads/${leadId}`)
  return data
}

export async function closeLead(leadId: number, statusId: number): Promise<LeadDetail> {
  const { data } = await http.post<LeadDetail>(`/leads/${leadId}/close`, {
    status_id: statusId,
  })
  return data
}

export async function listStatuses(params?: {
  kind?: StatusKind
}): Promise<StatusListResponse> {
  const query: Record<string, string> = {}
  if (params?.kind) query.kind = params.kind
  const { data } = await http.get<StatusListResponse>('/statuses', { params: query })
  return data
}

export async function patchLead(leadId: number, body: LeadPatchBody): Promise<LeadDetail> {
  const { data } = await http.patch<LeadDetail>(`/leads/${leadId}`, body)
  return data
}
