import { logger } from '@/shared/lib/logger'

export type NotificationPermissionState = NotificationPermission | 'unsupported'

export function isNotificationSupported(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window
}

export function getNotificationPermission(): NotificationPermissionState {
  if (!isNotificationSupported()) return 'unsupported'
  return Notification.permission
}

export async function requestNotificationPermission(): Promise<NotificationPermissionState> {
  if (!isNotificationSupported()) return 'unsupported'
  if (Notification.permission === 'granted') return 'granted'
  if (Notification.permission === 'denied') return 'denied'
  try {
    return await Notification.requestPermission()
  } catch (err) {
    logger.warn('notification permission request failed', err)
    return Notification.permission
  }
}

export function notifyInboundChatMessage(options: {
  title: string
  body: string
  chatId: number
}): void {
  if (!isNotificationSupported()) return
  if (Notification.permission !== 'granted') return
  if (!document.hidden) return

  try {
    const notification = new Notification(options.title, {
      body: options.body,
      tag: `chat-${options.chatId}`,
    })
    notification.onclick = () => {
      window.focus()
      notification.close()
    }
  } catch (err) {
    logger.warn('browser notification failed', err)
  }
}
