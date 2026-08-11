import { getRealtimeWS } from '@/shared/realtime/ws-client'

const TASK_TOPICS = [
  'task.created',
  'task.updated',
  'task.done_pending',
  'task.confirmed',
  'task.due_soon',
  'task.notify',
] as const

type TaskTopic = (typeof TASK_TOPICS)[number]

type TaskEventHandler = (topic: TaskTopic, payload: Record<string, unknown>) => void

let connected = false
const handlers = new Set<TaskEventHandler>()

export function onTasksEvent(handler: TaskEventHandler): () => void {
  handlers.add(handler)
  return () => handlers.delete(handler)
}

export async function connectTasksRealtime(): Promise<void> {
  if (connected) return
  const ws = getRealtimeWS()
  for (const topic of TASK_TOPICS) {
    ws.onTopic(topic, (payload) => {
      for (const handler of handlers) {
        handler(topic, payload as Record<string, unknown>)
      }
    })
  }
  connected = true
}

export function showTaskNotification(topic: TaskTopic, payload: Record<string, unknown>): string {
  const title = String(payload.title ?? 'Задача')
  switch (topic) {
    case 'task.created':
      return `Новая задача: ${title}`
    case 'task.due_soon':
      return `Срок задачи «${title}» подходит к концу`
    case 'task.done_pending':
      return `Задача на проверке: ${title}`
    case 'task.confirmed':
      return `Задача закрыта: ${title}`
    case 'task.updated':
      return `Задача обновлена: ${title}`
    case 'task.notify': {
      const fromName = String(payload.from_user_name || 'Коллега')
      const note = payload.message ? `: ${String(payload.message)}` : ''
      return `${fromName} просит внимания к задаче «${title}»${note}`
    }
    default:
      return title
  }
}
