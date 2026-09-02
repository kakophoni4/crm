import { http } from '@/shared/api/http'

export interface TelephonyAccount {
  id: number
  name: string
  provider: string
  department_id: number
  department_name: string | null
  group_id: number | null
  group_name: string | null
  group_ids: number[]
  group_names: string[]
  sip_host: string
  sip_port: number
  sip_transport: 'udp' | 'tcp' | 'tls'
  sip_username: string
  has_sip_password: boolean
  outbound_caller_id: string | null
  pbx_extension_prefix: string | null
  webrtc_ws_url: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface TelephonyAccountCreateBody {
  name: string
  provider?: string
  department_id: number
  group_id?: number | null
  group_ids?: number[]
  sip_host: string
  sip_port?: number
  sip_transport?: 'udp' | 'tcp' | 'tls'
  sip_username: string
  sip_password: string
  outbound_caller_id?: string | null
  pbx_extension_prefix?: string | null
  webrtc_ws_url?: string | null
}

export interface TelephonyAccountUpdateBody {
  name?: string
  group_id?: number | null
  group_ids?: number[]
  sip_host?: string
  sip_port?: number
  sip_transport?: 'udp' | 'tcp' | 'tls'
  sip_username?: string
  sip_password?: string
  outbound_caller_id?: string | null
  pbx_extension_prefix?: string | null
  webrtc_ws_url?: string | null
  is_active?: boolean
}

export interface TelephonyWebrtcConfig {
  account_id: number
  account_name: string
  extension: string
  extension_password: string
  extension_created: boolean
  display_name: string | null
  sip_uri: string
  ws_url: string
  outbound_caller_id: string | null
  ice_servers: RTCIceServer[]
}

export type TelephonyCallStatus = 'calling' | 'answered' | 'completed' | 'failed'

export interface TelephonyCall {
  id: number
  account_id: number
  account_name: string
  user_id: number
  user_name: string | null
  department_id: number
  department_name: string | null
  group_id: number | null
  group_name: string | null
  direction: 'outbound' | 'inbound'
  phone_number: string
  status: TelephonyCallStatus
  duration_seconds: number | null
  started_at: string
  answered_at: string | null
  ended_at: string | null
}

export async function listTelephonyAccounts(): Promise<TelephonyAccount[]> {
  const { data } = await http.get<{ items: TelephonyAccount[] }>('/telephony/accounts')
  return data.items
}

export async function createTelephonyAccount(
  body: TelephonyAccountCreateBody,
): Promise<TelephonyAccount> {
  const { data } = await http.post<TelephonyAccount>('/telephony/accounts', body)
  return data
}

export async function listTelephonyCalls(): Promise<TelephonyCall[]> {
  const { data } = await http.get<{ items: TelephonyCall[] }>('/telephony/calls')
  return data.items
}

export async function createTelephonyCall(
  accountId: number,
  phoneNumber: string,
): Promise<TelephonyCall> {
  const { data } = await http.post<TelephonyCall>('/telephony/calls', {
    account_id: accountId,
    phone_number: phoneNumber,
  })
  return data
}

export async function updateTelephonyCall(
  id: number,
  status: TelephonyCallStatus,
  durationSeconds?: number | null,
): Promise<TelephonyCall> {
  const { data } = await http.patch<TelephonyCall>(`/telephony/calls/${id}`, {
    status,
    duration_seconds: durationSeconds ?? null,
  })
  return data
}

export async function clearTelephonyCalls(): Promise<number> {
  const { data } = await http.delete<{ deleted: number }>('/telephony/calls')
  return data.deleted
}

export async function updateTelephonyAccount(
  id: number,
  body: TelephonyAccountUpdateBody,
): Promise<TelephonyAccount> {
  const { data } = await http.patch<TelephonyAccount>(`/telephony/accounts/${id}`, body)
  return data
}

export async function deactivateTelephonyAccount(id: number): Promise<TelephonyAccount> {
  const { data } = await http.delete<TelephonyAccount>(`/telephony/accounts/${id}`)
  return data
}

export async function getTelephonyWebrtcConfig(
  accountId: number,
): Promise<TelephonyWebrtcConfig> {
  const { data } = await http.post<TelephonyWebrtcConfig>(
    `/telephony/accounts/${accountId}/webrtc-config`,
  )
  return data
}
