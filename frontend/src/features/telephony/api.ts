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
  ice_servers: Record<string, unknown>[]
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
