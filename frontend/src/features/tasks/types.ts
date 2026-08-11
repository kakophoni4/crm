export type TaskType = 'urgent' | 'high' | 'normal' | 'low'
export type TaskStatus = 'new' | 'open' | 'done_pending' | 'closed'

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
  source?: string
  opt_unit_id?: number | null
  opt_requirement_id?: number | null
  chat_id?: number | null
  lead_id?: number | null
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
  needs_ack?: boolean
  creator: TaskUserBrief | null
  assignee: TaskUserBrief | null
  file_ids?: number[]
  files?: TaskFileBrief[]
}

export interface TaskFileBrief {
  id: number
  original_name: string
  mime_type: string
  size_bytes: number
}

export interface TaskComment {
  id: number
  task_id: number
  author_id: number
  body: string
  created_at: string
  author: TaskUserBrief | null
}

export interface TaskDetail extends DepartmentTask {
  comments: TaskComment[]
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
  department_id?: number
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
  urgent: '#dc2626',
  high: '#d97706',
  normal: '#2563eb',
  low: '#6b7280',
}
