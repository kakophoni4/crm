import type {
  EscalationPolicy,
  NotificationSettings,
  StaffNotificationEvent,
} from '@/features/notifications/api'
import { storage } from '@/shared/lib/storage'

const SETTINGS_TTL_MS = 5 * 60 * 1000
const HISTORY_TTL_MS = 2 * 60 * 1000

type SettingsCache = {
  fetchedAt: number
  settings: NotificationSettings
  escalation: EscalationPolicy | null
  hasToken: boolean
}

type HistoryCache = {
  fetchedAt: number
  status: string
  items: StaffNotificationEvent[]
}

function settingsKey(userId: number): string {
  return `crm.notifications.settings.v1.${userId}`
}

function historyKey(userId: number): string {
  return `crm.notifications.history.v1.${userId}`
}

export function peekNotificationSettingsCache(userId: number | null | undefined): SettingsCache | null {
  if (userId == null) return null
  const raw = storage.get(settingsKey(userId))
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as SettingsCache
    if (!parsed?.settings || typeof parsed.fetchedAt !== 'number') return null
    return parsed
  } catch {
    return null
  }
}

export function isNotificationSettingsFresh(userId: number | null | undefined): boolean {
  const cached = peekNotificationSettingsCache(userId)
  if (!cached) return false
  return Date.now() - cached.fetchedAt < SETTINGS_TTL_MS
}

export function setNotificationSettingsCache(
  userId: number,
  payload: {
    settings: NotificationSettings
    escalation: EscalationPolicy | null
    hasToken: boolean
  },
): void {
  const data: SettingsCache = {
    fetchedAt: Date.now(),
    settings: payload.settings,
    escalation: payload.escalation,
    hasToken: payload.hasToken,
  }
  storage.set(settingsKey(userId), JSON.stringify(data))
}

export function peekNotificationHistoryCache(
  userId: number | null | undefined,
  status = '',
): HistoryCache | null {
  if (userId == null) return null
  const raw = storage.get(historyKey(userId))
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as HistoryCache
    if (!parsed?.items || typeof parsed.fetchedAt !== 'number') return null
    if ((parsed.status || '') !== (status || '')) return null
    return parsed
  } catch {
    return null
  }
}

export function isNotificationHistoryFresh(
  userId: number | null | undefined,
  status = '',
): boolean {
  const cached = peekNotificationHistoryCache(userId, status)
  if (!cached) return false
  return Date.now() - cached.fetchedAt < HISTORY_TTL_MS
}

export function setNotificationHistoryCache(
  userId: number,
  status: string,
  items: StaffNotificationEvent[],
): void {
  const data: HistoryCache = {
    fetchedAt: Date.now(),
    status: status || '',
    items,
  }
  storage.set(historyKey(userId), JSON.stringify(data))
}
