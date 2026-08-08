import { http } from '@/shared/api/http'

import type {
  DepartmentTask,
  TaskBoard,
  TaskCreateBody,
  TaskStatus,
  TaskUpdateBody,
} from './types'

export type {
  DepartmentTask,
  TaskBoard,
  TaskCreateBody,
  TaskStatus,
  TaskType,
  TaskUpdateBody,
} from './types'

export async function listMyTasks(): Promise<{ items: DepartmentTask[]; total: number }> {
  const { data } = await http.get<{ items: DepartmentTask[]; total: number }>('/tasks/mine')
  return data
}

export async function getTaskBoard(departmentId?: number): Promise<TaskBoard> {
  const { data } = await http.get<TaskBoard>('/tasks/board', {
    params: departmentId != null ? { department_id: departmentId } : undefined,
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

export async function completeTask(taskId: number): Promise<DepartmentTask> {
  const { data } = await http.post<DepartmentTask>(`/tasks/${taskId}/complete`)
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

export async function deleteTask(taskId: number): Promise<void> {
  await http.delete(`/tasks/${taskId}`)
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

export async function listClientRequirementUnits(): Promise<
  { id: number; inn: string; name: string }[]
> {
  const { data } = await http.get<{ items: { id: number; inn: string; name: string }[] }>(
    '/tasks/client-requirement-units',
  )
  return data.items
}

export async function createClientRequirement(body: {
  unit_id: number
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
