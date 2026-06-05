import { http } from '@/shared/api/http'

export type UserDeletionRequestState = 'pending' | 'approved' | 'rejected'

export interface UserDeletionRequest {
  id: number
  target_user_id: number
  requested_by_user_id: number
  state: UserDeletionRequestState
  comment: string | null
  admin_comment: string | null
  decided_at: string | null
  decided_by_user_id: number | null
  created_at: string
  updated_at: string
  target_full_name: string | null
  requested_by_full_name: string | null
}

export async function createUserDeletionRequest(
  userId: number,
  body?: { comment?: string | null },
): Promise<UserDeletionRequest> {
  const { data } = await http.post<UserDeletionRequest>(
    `/users/${userId}/deletion-request`,
    body ?? {},
  )
  return data
}

export async function listUserDeletionRequests(
  state?: UserDeletionRequestState,
): Promise<UserDeletionRequest[]> {
  const params = state != null ? { state } : undefined
  const { data } = await http.get<{ items: UserDeletionRequest[] }>(
    '/user-deletion-requests',
    { params },
  )
  return data.items
}

export async function approveUserDeletionRequest(requestId: number): Promise<UserDeletionRequest> {
  const { data } = await http.post<UserDeletionRequest>(
    `/user-deletion-requests/${requestId}/approve`,
  )
  return data
}

export async function rejectUserDeletionRequest(
  requestId: number,
  body?: { admin_comment?: string | null },
): Promise<UserDeletionRequest> {
  const { data } = await http.post<UserDeletionRequest>(
    `/user-deletion-requests/${requestId}/reject`,
    body ?? {},
  )
  return data
}

export async function adminRemoveUser(userId: number): Promise<void> {
  await http.post(`/users/${userId}/remove`)
}
