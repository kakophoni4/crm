import { http } from '@/shared/api/http'

import type {
  DepartmentTask,
  TaskBoard,
  TaskCreateBody,
  TaskUpdateBody,
} from './types'

export type {
  DepartmentTask,
  TaskBoard,
  TaskCreateBody,
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
