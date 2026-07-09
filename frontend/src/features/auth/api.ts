import { http } from '@/shared/api/http'

export type UserRole = 'user' | 'senior' | 'admin' | 'accountant'

export interface AuthUserSummary {
  id: number
  email: string
  full_name: string
  role: UserRole
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: AuthUserSummary
}

export interface TokenPairResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export type UserPresence = 'online' | 'away' | 'busy' | 'offline'

export interface MeResponse {
  id: number
  email: string
  full_name: string
  role: UserRole
  department_id: number | null
  group_id: number | null
  group_ids: number[]
  presence: UserPresence
  permissions: string[]
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const { data } = await http.post<LoginResponse>('/auth/login', { username, password })
  return data
}

export async function refresh(refreshToken: string): Promise<TokenPairResponse> {
  const { data } = await http.post<TokenPairResponse>('/auth/refresh', {
    refresh_token: refreshToken,
  })
  return data
}

export async function logout(refreshToken: string): Promise<void> {
  await http.post('/auth/logout', { refresh_token: refreshToken })
}

export async function me(): Promise<MeResponse> {
  const { data } = await http.get<MeResponse>('/auth/me')
  return data
}

export async function fetchWsTicket(): Promise<{ ticket: string; expires_in: number }> {
  const { data } = await http.post<{ ticket: string; expires_in: number }>('/auth/ws-ticket')
  return data
}
