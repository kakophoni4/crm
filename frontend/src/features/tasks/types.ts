export type TaskType = 'urgent' | 'high' | 'normal' | 'low'
export type TaskStatus = 'open' | 'done_pending' | 'closed'

export interface TaskUserBrief {
  id: number
  full_name: string
}

export interface DepartmentTask {
  id: number
  department_id: number
  title: string
  description: string | null
  task_type: TaskType
  task_type_label: string
  status: TaskStatus
  created_by: number
  assignee_id: number
  due_at: string | null
  completed_at: string | null
  completed_by: number | null
  confirmed_at: string | null
  confirmed_by: number | null
  created_at: string
  updated_at: string
  is_overdue: boolean
  due_soon: boolean
  creator: TaskUserBrief | null
  assignee: TaskUserBrief | null
}

export interface TaskBoardColumn {
  status: string
  label: string
  items: DepartmentTask[]
}

export interface TaskBoard {
  columns: TaskBoardColumn[]
  task_types: { value: string; label: string; sort_order: number }[]
}

export interface TaskCreateBody {
  title: string
  description?: string | null
  task_type: TaskType
  assignee_id: number
  due_at?: string | null
}

export interface TaskUpdateBody {
  title?: string
  description?: string | null
  task_type?: TaskType
  assignee_id?: number
  due_at?: string | null
}

export const TASK_TYPE_COLORS: Record<TaskType, string> = {
  urgent: '#d03050',
  high: '#f0a020',
  normal: '#2080f0',
  low: '#909399',
}
