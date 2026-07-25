import type {
  Contact,
  ContactAuditResponse,
  ContactCreateBody,
  ContactListParams,
  ContactListResponse,
  ContactTransferListResponse,
  ContactTransferRecord,
  ContactTransferRequestBody,
  ContactUpdateBody,
  EscalationSettings,
  EscalationSettingsPatch,
  AfterHoursSettings,
  AfterHoursSettingsPatch,
  ContactActivityResponse,
  ReplyAuditListResponse,
} from '@/entities/contact/types'
import { http } from '@/shared/api/http'

function buildListParams(params: ContactListParams): Record<string, string | number> {
  const query: Record<string, string | number> = {}
  if (params.q) query.q = params.q
  if (params.status) query.status = params.status
  if (params.cursor) query.cursor = params.cursor
  if (params.offset != null) query.offset = params.offset
  if (params.limit) query.limit = params.limit
  if (params.include_total) query.include_total = 'true'
  if (params.custom_field_filters) {
    for (const [key, value] of Object.entries(params.custom_field_filters)) {
      if (value) query[`custom_field[${key}]`] = value
    }
  }
  return query
}

let listContactsAbort: AbortController | null = null

export async function listContacts(params: ContactListParams): Promise<ContactListResponse> {
  listContactsAbort?.abort()
  listContactsAbort = new AbortController()
  const signal = listContactsAbort.signal
  const { data } = await http.get<ContactListResponse>('/contacts', {
    params: buildListParams(params),
    signal,
  })
  return data
}

export async function getContact(id: number): Promise<Contact> {
  const { data } = await http.get<Contact>(`/contacts/${id}`)
  return data
}

export async function createContact(body: ContactCreateBody): Promise<Contact> {
  const { data } = await http.post<Contact>('/contacts', body)
  return data
}

export async function updateContact(id: number, body: ContactUpdateBody): Promise<Contact> {
  const { data } = await http.patch<Contact>(`/contacts/${id}`, body)
  return data
}

export async function getContactHistory(
  id: number,
  limit = 100,
): Promise<ContactActivityResponse> {
  const { data } = await http.get<ContactActivityResponse>(`/contacts/${id}/history`, {
    params: { limit },
  })
  return data
}

export async function getContactAudit(id: number, limit = 100): Promise<ContactAuditResponse> {
  const { data } = await http.get<ContactAuditResponse>(`/contacts/${id}/audit`, {
    params: { limit },
  })
  return data
}

export async function requestContactTransfer(
  contactId: number,
  groupId: number,
  body: ContactTransferRequestBody,
): Promise<ContactTransferRecord> {
  const { data } = await http.post<ContactTransferRecord>(
    `/contacts/${contactId}/groups/${groupId}/transfers`,
    body,
  )
  return data
}

export async function listContactTransfers(params: {
  state?: string
  group_id?: number
} = {}): Promise<ContactTransferListResponse> {
  const { data } = await http.get<ContactTransferListResponse>('/contact-transfers', { params })
  return data
}

export async function approveContactTransfer(
  transferId: number,
  expectedVersion: number,
): Promise<ContactTransferRecord> {
  const { data } = await http.post<ContactTransferRecord>(
    `/contact-transfers/${transferId}/approve`,
    undefined,
    { params: { expected_version: expectedVersion } },
  )
  return data
}

export async function declineContactTransfer(transferId: number): Promise<ContactTransferRecord> {
  const { data } = await http.post<ContactTransferRecord>(
    `/contact-transfers/${transferId}/decline`,
  )
  return data
}

export async function acceptContactTransfer(
  transferId: number,
  expectedVersion: number,
): Promise<ContactTransferRecord> {
  const { data } = await http.post<ContactTransferRecord>(
    `/contact-transfers/${transferId}/accept`,
    undefined,
    { params: { expected_version: expectedVersion } },
  )
  return data
}

export async function rejectContactTransfer(transferId: number): Promise<ContactTransferRecord> {
  const { data } = await http.post<ContactTransferRecord>(
    `/contact-transfers/${transferId}/reject`,
  )
  return data
}

export async function cancelContactTransfer(transferId: number): Promise<ContactTransferRecord> {
  const { data } = await http.post<ContactTransferRecord>(
    `/contact-transfers/${transferId}/cancel`,
  )
  return data
}

export async function getReplyAudit(
  contactId: number,
  groupId: number,
  limit = 200,
): Promise<ReplyAuditListResponse> {
  const { data } = await http.get<ReplyAuditListResponse>(
    `/contacts/${contactId}/groups/${groupId}/reply-audit`,
    { params: { limit } },
  )
  return data
}

export async function getEscalationSettings(groupId: number): Promise<EscalationSettings> {
  const { data } = await http.get<EscalationSettings>(`/groups/${groupId}/escalation-settings`)
  return data
}

export async function patchEscalationSettings(
  groupId: number,
  body: EscalationSettingsPatch,
): Promise<EscalationSettings> {
  const { data } = await http.patch<EscalationSettings>(
    `/groups/${groupId}/escalation-settings`,
    body,
  )
  return data
}

export async function getAfterHoursSettings(groupId: number): Promise<AfterHoursSettings> {
  const { data } = await http.get<AfterHoursSettings>(`/groups/${groupId}/after-hours-settings`)
  return data
}

export async function patchAfterHoursSettings(
  groupId: number,
  body: AfterHoursSettingsPatch,
): Promise<AfterHoursSettings> {
  const { data } = await http.patch<AfterHoursSettings>(
    `/groups/${groupId}/after-hours-settings`,
    body,
  )
  return data
}
