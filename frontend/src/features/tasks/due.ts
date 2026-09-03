import type { DepartmentTask, TaskType } from './types'

export type TaskSortMode = 'due' | 'priority' | 'created'
export type TaskDueTone = 'overdue' | 'soon' | 'ok' | 'none'

export const TASK_TYPE_SORT_ORDER: Record<TaskType, number> = {
  urgent: 0,
  high: 1,
  normal: 2,
  low: 3,
}

const DAY_MS = 86_400_000
const HOUR_MS = 3_600_000
const MINUTE_MS = 60_000

export function pluralDays(n: number): string {
  const abs = Math.abs(n) % 100
  const d = abs % 10
  if (abs > 10 && abs < 20) return 'дней'
  if (d === 1) return 'день'
  if (d >= 2 && d <= 4) return 'дня'
  return 'дней'
}

export function isClosedTaskStatus(status: string): boolean {
  return status === 'closed' || status === 'deleted'
}

export function taskDueTimestamp(dueAt: string | null | undefined): number | null {
  if (!dueAt) return null
  const ts = new Date(dueAt).getTime()
  return Number.isFinite(ts) ? ts : null
}

/** Просрочена, если срок уже прошёл и задача ещё не закрыта. */
export function taskIsOverdue(task: Pick<DepartmentTask, 'due_at' | 'status'>, now = Date.now()): boolean {
  if (isClosedTaskStatus(task.status)) return false
  const due = taskDueTimestamp(task.due_at)
  return due != null && due < now
}

export function taskDeadline(
  dueAt: string | null | undefined,
  now = Date.now(),
): { text: string; tone: TaskDueTone } {
  const due = taskDueTimestamp(dueAt)
  if (due == null) return { text: 'без срока', tone: 'none' }
  const diff = due - now
  if (diff < 0) {
    const days = Math.max(1, Math.ceil(Math.abs(diff) / DAY_MS))
    return { text: `просрочено на ${days} ${pluralDays(days)}`, tone: 'overdue' }
  }
  const days = Math.floor(diff / DAY_MS)
  const hours = Math.floor((diff % DAY_MS) / HOUR_MS)
  if (days <= 0) {
    if (hours <= 0) {
      const mins = Math.max(1, Math.floor(diff / MINUTE_MS))
      return { text: `осталось ${mins} мин`, tone: 'soon' }
    }
    return { text: `осталось ${hours} ч`, tone: 'soon' }
  }
  if (days <= 3) {
    return { text: `осталось ${days} ${pluralDays(days)}`, tone: 'soon' }
  }
  return { text: `осталось ${days} ${pluralDays(days)}`, tone: 'ok' }
}

function dueSortParts(task: Pick<DepartmentTask, 'due_at'>, now: number): { bucket: number; ts: number } {
  const due = taskDueTimestamp(task.due_at)
  if (due == null) return { bucket: 2, ts: Number.POSITIVE_INFINITY }
  return { bucket: due < now ? 0 : 1, ts: due }
}

export function sortTasks<T extends Pick<DepartmentTask, 'id' | 'task_type' | 'due_at' | 'created_at'>>(
  tasks: T[],
  mode: TaskSortMode = 'due',
  now = Date.now(),
): T[] {
  return [...tasks].sort((a, b) => {
    if (mode === 'created') {
      const created = new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      return created || b.id - a.id
    }
    const typeA = TASK_TYPE_SORT_ORDER[a.task_type] ?? 99
    const typeB = TASK_TYPE_SORT_ORDER[b.task_type] ?? 99
    if (mode === 'priority' && typeA !== typeB) return typeA - typeB
    const pa = dueSortParts(a, now)
    const pb = dueSortParts(b, now)
    if (pa.bucket !== pb.bucket) return pa.bucket - pb.bucket
    if (pa.ts !== pb.ts) return pa.ts - pb.ts
    if (mode === 'due' && typeA !== typeB) return typeA - typeB
    return b.id - a.id
  })
}
