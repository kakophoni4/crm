export type TaskType = 'urgent' | 'high' | 'normal' | 'low'
export type TaskStatus = 'new' | 'open' | 'done_pending' | 'closed' | 'deleted'

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
  parent_task_id?: number | null
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
  collaborators?: TaskUserBrief[]
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

export interface TaskChildBrief {
  id: number
  title: string
  status: string
  assignee: TaskUserBrief | null
}

export interface TaskDetail extends DepartmentTask {
  comments: TaskComment[]
  child_tasks?: TaskChildBrief[]
}

export interface TaskBoardColumn {
  status: string
  label: string
  items: DepartmentTask[]
}

export interface TaskWorkloadSummary {
  total: number
  new: number
  open: number
  overdue: number
  pending_review: number
  done: number
  deleted?: number
}

export interface TaskHistoryItem {
  id: number
  action: string
  summary: string
  payload: Record<string, unknown>
  created_at: string
  actor: TaskUserBrief | null
}

export interface TaskBoard {
  columns: TaskBoardColumn[]
  task_types: { value: string; label: string; sort_order: number }[]
  summary?: TaskWorkloadSummary
}

export interface TaskListQuery {
  assignee_id?: number | null
  created_by?: number | null
  q?: string | null
  status?: TaskStatus | null
  include_closed?: boolean
}

export interface TaskCreateBody {
  title: string
  description?: string | null
  task_type: TaskType
  assignee_id: number
  department_id?: number
  due_at?: string | null
  file_ids?: number[]
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

const ROLE_SHORT_LABEL: Record<string, string> = {
  user: 'оператор',
  senior: 'старший',
  group_senior: 'ст. группы',
  admin: 'админ',
  accountant: 'бухгалтер',
  chief_accountant: 'главбух',
  lawyer: 'юрист',
}

export interface TaskAssigneeOption {
  id: number
  full_name: string
  role?: string
  department_id?: number | null
}

export function formatTaskAssigneeLabel(
  user: { id: number; full_name: string; role?: string },
  meId?: number | null,
): string {
  const role = user.role ? ROLE_SHORT_LABEL[user.role] || user.role : ''
  const name = role ? `${user.full_name} · ${role}` : user.full_name
  return meId != null && user.id === meId ? `Себе (${name})` : name
}
