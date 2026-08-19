import { http } from '@/shared/api/http'

import type {
  DepartmentTask,
  TaskAssigneeOption,
  TaskBoard,
  TaskComment,
  TaskCreateBody,
  TaskDetail,
  TaskHistoryItem,
  TaskListQuery,
  TaskStatus,
  TaskUpdateBody,
  TaskWorkloadSummary,
} from './types'

export type {
  DepartmentTask,
  TaskAssigneeOption,
  TaskBoard,
  TaskComment,
  TaskCreateBody,
  TaskDetail,
  TaskHistoryItem,
  TaskListQuery,
  TaskStatus,
  TaskType,
  TaskUpdateBody,
  TaskWorkloadSummary,
} from './types'
export { formatTaskAssigneeLabel } from './types'

function toTaskQueryParams(query?: TaskListQuery): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = {}
  if (!query) return params
  if (query.assignee_id != null) params.assignee_id = query.assignee_id
  if (query.created_by != null) params.created_by = query.created_by
  if (query.q?.trim()) params.q = query.q.trim()
  if (query.status) params.status = query.status
  if (query.include_closed === true) params.include_closed = true
  if (query.include_closed === false) params.include_closed = false
  return params
}

export async function listMyTasks(
  query?: TaskListQuery,
): Promise<{ items: DepartmentTask[]; total: number; summary?: TaskWorkloadSummary }> {
  const { data } = await http.get<{
    items: DepartmentTask[]
    total: number
    summary?: TaskWorkloadSummary
  }>('/tasks/mine', { params: toTaskQueryParams(query) })
  return data
}

export async function listTaskAssignees(): Promise<TaskAssigneeOption[]> {
  const { data } = await http.get<{ items: TaskAssigneeOption[] }>('/tasks/assignees')
  return data.items ?? []
}

export async function getTaskBoard(departmentId?: number, query?: TaskListQuery): Promise<TaskBoard> {
  const { data } = await http.get<TaskBoard>('/tasks/board', {
    params: {
      ...(departmentId != null ? { department_id: departmentId } : {}),
      ...toTaskQueryParams(query),
    },
  })
  return data
}

export async function createTask(body: TaskCreateBody): Promise<DepartmentTask> {
  const { data } = await http.post<DepartmentTask>('/tasks', body)
  return data
}

export async function updateTask(taskId: number, body: TaskUpdateBody): Promise<DepartmentTask> {
  const { data } = await http.patch<DepartmentTask>(`/tasks/${taskId}`, body)
  return data
}

export async function moveTask(
  taskId: number,
  status: TaskStatus,
  position: number,
): Promise<DepartmentTask> {
  const { data } = await http.post<DepartmentTask>(`/tasks/${taskId}/move`, { status, position })
  return data
}

export async function completeTask(
  taskId: number,
  body?: { comment?: string | null; file_ids?: number[] },
): Promise<DepartmentTask> {
  const { data } = await http.post<DepartmentTask>(`/tasks/${taskId}/complete`, body ?? {})
  return data
}

export async function confirmTask(taskId: number): Promise<DepartmentTask> {
  const { data } = await http.post<DepartmentTask>(`/tasks/${taskId}/confirm`)
  return data
}

export async function reopenTask(taskId: number): Promise<DepartmentTask> {
  const { data } = await http.post<DepartmentTask>(`/tasks/${taskId}/reopen`)
  return data
}

export async function deleteTask(taskId: number, options?: { permanent?: boolean }): Promise<void> {
  await http.delete(`/tasks/${taskId}`, {
    params: options?.permanent ? { permanent: true } : undefined,
  })
}

export async function fetchTaskAlerts(): Promise<{
  blink: boolean
  due_soon: number
  overdue: number
  unacked_fns: number
  client_due: number
}> {
  const { data } = await http.get<{
    blink: boolean
    due_soon: number
    overdue: number
    unacked_fns: number
    client_due: number
  }>('/tasks/alerts')
  return data
}

export async function acknowledgeTask(taskId: number): Promise<DepartmentTask> {
  const { data } = await http.post<DepartmentTask>(`/tasks/${taskId}/acknowledge`)
  return data
}

export async function getTask(taskId: number): Promise<TaskDetail> {
  const { data } = await http.get<TaskDetail>(`/tasks/${taskId}`)
  return data
}

export async function getTaskHistory(taskId: number): Promise<TaskHistoryItem[]> {
  const { data } = await http.get<{ items: TaskHistoryItem[] }>(`/tasks/${taskId}/history`)
  return data.items ?? []
}

export async function addTaskComment(
  taskId: number,
  body: string,
  fileIds?: number[],
): Promise<TaskComment> {
  const { data } = await http.post<TaskComment>(`/tasks/${taskId}/comments`, {
    body,
    file_ids: fileIds ?? [],
  })
  return data
}

export async function attachTaskFiles(
  taskId: number,
  fileIds: number[],
): Promise<DepartmentTask> {
  const { data } = await http.post<DepartmentTask>(`/tasks/${taskId}/files`, {
    file_ids: fileIds,
  })
  return data
}

export async function handoffTask(
  taskId: number,
  body: {
    action: 'add' | 'transfer' | 'follow_up'
    user_id: number
    comment?: string | null
    file_ids?: number[]
    follow_up_title?: string | null
    follow_up_description?: string | null
    follow_up_due_at?: string | null
  },
): Promise<DepartmentTask> {
  const { data } = await http.post<DepartmentTask>(`/tasks/${taskId}/handoff`, body)
  return data
}

export async function notifyTaskAssignee(
  taskId: number,
  message?: string | null,
): Promise<void> {
  await http.post(`/tasks/${taskId}/notify-assignee`, { message: message ?? null })
}

export async function notifyTaskCreator(
  taskId: number,
  message?: string | null,
): Promise<void> {
  await http.post(`/tasks/${taskId}/notify-creator`, { message: message ?? null })
}

export async function listClientRequirementUnits(): Promise<{
  items: {
    id: number
    inn: string
    name: string
    accountant_user_id?: number | null
  }[]
  accountants: { id: number; full_name: string; role?: string }[]
  assignees: { id: number; full_name: string; role?: string }[]
}> {
  const { data } = await http.get<{
    items: {
      id: number
      inn: string
      name: string
      accountant_user_id?: number | null
    }[]
    accountants: { id: number; full_name: string; role?: string }[]
    assignees?: { id: number; full_name: string; role?: string }[]
  }>('/tasks/client-requirement-units')
  const people = data.assignees?.length ? data.assignees : (data.accountants ?? [])
  return {
    items: data.items,
    accountants: people,
    assignees: people,
  }
}

export async function createClientRequirement(body: {
  unit_id: number
  assignee_id?: number | null
  title: string
  description?: string | null
  due_at?: string | null
  file_ids?: number[]
  chat_id?: number | null
  lead_id?: number | null
}): Promise<DepartmentTask> {
  const { data } = await http.post<DepartmentTask>('/tasks/client-requirements', body)
  return data
}

export async function listClientRequirementsByChat(
  chatId: number,
): Promise<{ items: DepartmentTask[]; total: number }> {
  const { data } = await http.get<{ items: DepartmentTask[]; total: number }>(
    `/tasks/by-chat/${chatId}`,
  )
  return data
}
