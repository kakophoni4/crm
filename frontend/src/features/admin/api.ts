import { http } from '@/shared/api/http'

export interface Department {
  id: number
  name: string
  head_user_id: number | null
  created_at: string
  updated_at: string
}

export interface Group {
  id: number
  name: string
  department_id: number
  created_at: string
  updated_at: string
}

export interface AdminUser {
  id: number
  email: string
  username: string
  full_name: string
  role: 'user' | 'senior' | 'admin'
  department_id: number | null
  group_id: number | null
  status: 'active' | 'disabled'
  presence: string
  availability: string
  created_at: string
  updated_at: string
}

export interface StatusItem {
  id: number
  code: string
  kind: 'chat_label' | 'lead_pipeline'
  label: string
  color: string | null
  sort_order: number
  is_active: boolean
}

export interface BotItem {
  id: number
  code: string
  name: string
  owner_type: 'department' | 'group'
  owner_id: number
  outbound_url: string
  health_url: string | null
  is_active: boolean
}

export interface BotCreateBody {
  code: string
  name: string
  owner_type: 'department' | 'group'
  owner_id: number
  outbound_url: string
  inbound_secret: string
  outbound_secret: string
  health_url?: string | null
}

export interface BotCreateResponse extends BotItem {
  secrets?: {
    inbound_secret: string
    outbound_secret: string
    warning: string
  }
}

export async function listDepartments(): Promise<Department[]> {
  const { data } = await http.get<{ items: Department[] }>('/departments')
  return data.items
}

export async function createDepartment(body: {
  name: string
  head_user_id?: number | null
}): Promise<Department> {
  const { data } = await http.post<Department>('/departments', body)
  return data
}

export async function updateDepartment(
  id: number,
  body: { name?: string; head_user_id?: number | null },
): Promise<Department> {
  const { data } = await http.patch<Department>(`/departments/${id}`, body)
  return data
}

export async function deleteDepartment(id: number): Promise<Department> {
  const { data } = await http.delete<Department>(`/departments/${id}`)
  return data
}

export async function listGroups(departmentId?: number): Promise<Group[]> {
  const params = departmentId != null ? { department_id: departmentId } : undefined
  const { data } = await http.get<{ items: Group[] }>('/groups', { params })
  return data.items
}

export async function createGroup(body: {
  name: string
  department_id: number
}): Promise<Group> {
  const { data } = await http.post<Group>('/groups', body)
  return data
}

export async function updateGroup(id: number, body: { name?: string }): Promise<Group> {
  const { data } = await http.patch<Group>(`/groups/${id}`, body)
  return data
}

export async function deleteGroup(id: number): Promise<Group> {
  const { data } = await http.delete<Group>(`/groups/${id}`)
  return data
}

export async function listUsers(params?: {
  department_id?: number
  group_id?: number
  q?: string
}): Promise<AdminUser[]> {
  const { data } = await http.get<{ items: AdminUser[] }>('/users', { params })
  return data.items
}

export async function createUser(body: {
  username: string
  full_name: string
  password: string
  role: 'user' | 'senior' | 'admin'
  group_id: number | null
}): Promise<AdminUser> {
  const { data } = await http.post<AdminUser>('/users', body)
  return data
}

export async function updateUser(
  id: number,
  body: Partial<Pick<AdminUser, 'full_name' | 'group_id' | 'role' | 'status'>>,
): Promise<AdminUser> {
  const { data } = await http.patch<AdminUser>(`/users/${id}`, body)
  return data
}

export async function resetUserPassword(id: number): Promise<{ temporary_password: string }> {
  const { data } = await http.post<{ temporary_password: string }>(
    `/users/${id}/reset-password`,
  )
  return data
}

export async function listBots(): Promise<BotItem[]> {
  const { data } = await http.get<{ items: BotItem[] }>('/bots')
  return data.items
}

export async function createBot(body: BotCreateBody): Promise<BotCreateResponse> {
  const { data } = await http.post<BotCreateResponse>('/bots', body)
  return data
}

export async function rotateBotSecret(
  botId: number,
  kind: 'inbound' | 'outbound',
): Promise<{ kind: string; secret: string }> {
  const { data } = await http.post<{ kind: string; secret: string }>(
    `/bots/${botId}/rotate-secret`,
    { kind },
  )
  return data
}

export async function listStatuses(params?: {
  kind?: 'chat_label' | 'lead_pipeline'
  include_inactive?: boolean
}): Promise<StatusItem[]> {
  const { data } = await http.get<{ items: StatusItem[] }>('/statuses', { params })
  return data.items
}

export async function createStatus(body: {
  code: string
  kind: 'chat_label' | 'lead_pipeline'
  label: string
  color?: string | null
  sort_order?: number
}): Promise<StatusItem> {
  const { data } = await http.post<StatusItem>('/statuses', body)
  return data
}

export async function updateStatus(
  id: number,
  body: { label?: string; color?: string | null; sort_order?: number },
): Promise<StatusItem> {
  const { data } = await http.patch<StatusItem>(`/statuses/${id}`, body)
  return data
}

export async function deleteStatus(id: number): Promise<StatusItem> {
  const { data } = await http.delete<StatusItem>(`/statuses/${id}`)
  return data
}
