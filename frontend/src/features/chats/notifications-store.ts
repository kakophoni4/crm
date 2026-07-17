import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { ensureGroupDirectory, lookupGroupName } from '@/features/groups/directory'
import { useChatsStore } from '@/features/chats/store'
import { playTransferInboxSound } from '@/shared/audio/transfer-inbox'
import { storage } from '@/shared/lib/storage'
import { useAuthStore } from '@/shared/store/auth'
import { connectRealtime, getRealtimeWS } from '@/shared/realtime/ws-client'

export type ChatNotificationTopic =
  | 'chat.message.inbound'
  | 'message.replied.on_behalf'
  | 'contact.escalation.group_notify'
  | 'contact.escalation.owner_notify'
  | 'contact.ownership.assigned'
  | 'contact.ownership.reassigned'
  | 'contact.ownership.transferred'

export type ChatNotificationItem = {
  id: string
  at: number
  topic: ChatNotificationTopic
  line: string
  chatId: number | null
  read: boolean
}

const MAX_ITEMS = 10
const MUTE_STORAGE_KEY = 'crm.staff.mute_phrases.v1'

function normalizeMutePhrases(raw: unknown): string[] {
  if (!Array.isArray(raw)) return []
  const seen = new Set<string>()
  const out: string[] = []
  for (const item of raw) {
    const phrase = String(item ?? '').trim()
    if (!phrase) continue
    const key = phrase.toLocaleLowerCase('ru-RU')
    if (seen.has(key)) continue
    seen.add(key)
    out.push(phrase)
  }
  return out.slice(0, 50)
}

export function textMatchesMutePhrases(text: string | null | undefined, phrases: string[]): boolean {
  const body = (text ?? '').trim()
  if (!body || !phrases.length) return false
  const lowered = body.toLocaleLowerCase('ru-RU')
  return phrases.some((phrase) => {
    const key = phrase.trim().toLocaleLowerCase('ru-RU')
    return key.length > 0 && lowered.includes(key)
  })
}
// owner_notify intentionally omitted: owners already get chat.message.inbound
const FEED_TOPICS: ChatNotificationTopic[] = [
  'message.replied.on_behalf',
  'contact.escalation.group_notify',
  'contact.ownership.assigned',
  'contact.ownership.reassigned',
  'contact.ownership.transferred',
]

function storageKey(userId: number | null | undefined): string {
  return userId != null ? `crm.chat.notifications.v1.${userId}` : 'crm.chat.notifications.v1'
}

function num(payload: Record<string, unknown>, key: string): number | null {
  const v = payload[key]
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

function str(payload: Record<string, unknown>, key: string): string | null {
  const v = payload[key]
  return typeof v === 'string' && v.trim() !== '' ? v : null
}

function contactLabel(payload: Record<string, unknown>): string {
  const name = str(payload, 'contact_full_name') ?? str(payload, 'contact_name')
  if (name) return `«${name}»`

  const chatId = num(payload, 'chat_id')
  if (chatId != null) {
    const fromList = useChatsStore().listItems.find((chat) => chat.id === chatId)?.contact_name
    if (fromList) return `«${fromList}»`
  }

  const id = num(payload, 'contact_id')
  return id != null ? `контакт #${id}` : 'карточка'
}

function groupSuffix(payload: Record<string, unknown>): string {
  const name = str(payload, 'group_name') ?? lookupGroupName(num(payload, 'group_id'))
  if (name) return ` · ${name}`
  return ''
}

function formatLine(topic: ChatNotificationTopic, payload: Record<string, unknown>): string {
  const contact = contactLabel(payload)
  const group = groupSuffix(payload)

  switch (topic) {
    case 'chat.message.inbound':
      return `Новое сообщение ${contact}${group}`
    case 'message.replied.on_behalf': {
      const who = str(payload, 'author_full_name') ?? 'Коллега'
      const preview = str(payload, 'text_preview')
      const piece = preview ? ` — «${preview}»` : ''
      return `Ответ за вас в чате ${contact}: ${who}${piece}${group}`
    }
    case 'contact.escalation.owner_notify':
      return `Новое входящее по вашей карточке ${contact}${group}`
    case 'contact.escalation.group_notify':
      return `Карточка ${contact} ждёт ответа в общей очереди${group}`
    case 'contact.ownership.assigned': {
      const owner = str(payload, 'owner_full_name') ?? 'оператор'
      return `Новая карточка ${contact} — владелец ${owner}${group}`
    }
    case 'contact.ownership.reassigned': {
      const from = str(payload, 'old_owner_full_name') ?? 'прежний владелец'
      const to = str(payload, 'new_owner_full_name') ?? 'новый владелец'
      const perspective = str(payload, 'perspective')
      const reason = str(payload, 'reason')
      const why =
        reason === 'timeout' ? ' (таймаут ответа)' : reason != null ? ` (${reason})` : ''
      if (perspective === 'former_owner') {
        return `С вас снята карточка ${contact}: новый владелец — ${to}${group}${why}`
      }
      if (perspective === 'new_owner') {
        return `Вам назначена карточка ${contact} (от ${from})${group}${why}`
      }
      return `Смена владельца ${contact}: ${from} → ${to}${group}${why}`
    }
    case 'contact.ownership.transferred': {
      const from = str(payload, 'from_user_full_name') ?? 'прежний владелец'
      const to =
        str(payload, 'to_user_full_name') ??
        str(payload, 'owner_full_name') ??
        'новый владелец'
      const perspective = str(payload, 'perspective')
      if (perspective === 'former_owner') {
        return `Вам передали карточку ${contact}: новый владелец — ${to}${group}`
      }
      if (perspective === 'new_owner') {
        return `Вам назначена карточка ${contact} (от ${from})${group}`
      }
      return `Смена владельца ${contact}: ${from} → ${to}${group}`
    }
    default:
      return `Событие: ${topic}`
  }
}

function dedupeKey(topic: ChatNotificationTopic, payload: Record<string, unknown>): string {
  const perspective = str(payload, 'perspective') ?? ''
  const messageId = num(payload, 'message_id') ?? ''
  return `${topic}:${num(payload, 'contact_id') ?? ''}:${num(payload, 'group_id') ?? ''}:${num(payload, 'chat_id') ?? ''}:${messageId}:${perspective}`
}

export const useChatNotificationsStore = defineStore('chat-notifications', () => {
  const items = ref<ChatNotificationItem[]>([])
  const mutePhrases = ref<string[]>([])
  const connected = ref(false)
  const recentDedupe = new Map<string, number>()
  let unsubscribers: (() => void)[] = []
  let loadedUserId: number | null = null

  const unreadCount = computed(() => items.value.filter((row) => !row.read).length)

  function loadMutePhrases(): void {
    const raw = storage.get(MUTE_STORAGE_KEY)
    if (!raw) {
      mutePhrases.value = []
      return
    }
    try {
      mutePhrases.value = normalizeMutePhrases(JSON.parse(raw))
    } catch {
      mutePhrases.value = []
    }
  }

  function setMutePhrases(phrases: string[]): void {
    mutePhrases.value = normalizeMutePhrases(phrases)
    storage.set(MUTE_STORAGE_KEY, JSON.stringify(mutePhrases.value))
  }

  function persist(): void {
    const auth = useAuthStore()
    storage.set(
      storageKey(auth.user?.id),
      JSON.stringify({ items: items.value.slice(0, MAX_ITEMS) }),
    )
  }

  function loadForCurrentUser(): void {
    const auth = useAuthStore()
    const userId = auth.user?.id ?? null
    if (loadedUserId === userId) return
    loadedUserId = userId
    loadMutePhrases()
    const raw = storage.get(storageKey(userId))
    if (!raw) {
      items.value = []
      return
    }
    try {
      const parsed = JSON.parse(raw) as { items?: ChatNotificationItem[] }
      items.value = Array.isArray(parsed.items)
        ? parsed.items
            .filter((row) => row && typeof row.id === 'string' && typeof row.line === 'string')
            .map((row) => ({
              id: row.id,
              at: Number(row.at) || Date.now(),
              topic: row.topic,
              line: row.line,
              chatId: row.chatId == null ? null : Number(row.chatId),
              read: Boolean(row.read),
            }))
            .slice(0, MAX_ITEMS)
        : []
    } catch {
      items.value = []
    }
  }

  function isDuplicate(key: string): boolean {
    const now = Date.now()
    const prev = recentDedupe.get(key)
    recentDedupe.set(key, now)
    if (prev != null && now - prev < 900) return true
    if (recentDedupe.size > 200) {
      for (const [k, t] of recentDedupe) {
        if (now - t > 60_000) recentDedupe.delete(k)
      }
    }
    return false
  }

  function push(
    topic: ChatNotificationTopic,
    payload: Record<string, unknown>,
    options: { playSound?: boolean } = {},
  ): void {
    loadForCurrentUser()
    const key = dedupeKey(topic, payload)
    if (isDuplicate(key)) return

    const chatId = num(payload, 'chat_id')
    const item: ChatNotificationItem = {
      id: `${topic}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      at: Date.now(),
      topic,
      line: formatLine(topic, payload),
      chatId,
      read: false,
    }
    items.value = [item, ...items.value].slice(0, MAX_ITEMS)
    persist()
    if (options.playSound ?? true) void playTransferInboxSound()
  }

  function pushInbound(payload: Record<string, unknown>): void {
    loadMutePhrases()
    const preview =
      (typeof payload.text_preview === 'string' && payload.text_preview) ||
      (typeof payload.text === 'string' && payload.text) ||
      ''
    if (textMatchesMutePhrases(preview, mutePhrases.value)) return

    loadForCurrentUser()
    const chatId = num(payload, 'chat_id')
    // One unread inbound per chat: refresh instead of stacking every message.
    if (chatId != null) {
      const existingIdx = items.value.findIndex(
        (row) => row.topic === 'chat.message.inbound' && row.chatId === chatId && !row.read,
      )
      if (existingIdx >= 0) {
        const refreshed: ChatNotificationItem = {
          ...items.value[existingIdx],
          at: Date.now(),
          line: formatLine('chat.message.inbound', payload),
          read: false,
        }
        const rest = items.value.filter((_, i) => i !== existingIdx)
        items.value = [refreshed, ...rest].slice(0, MAX_ITEMS)
        persist()
        void playTransferInboxSound()
        return
      }
    }
    push('chat.message.inbound', payload, { playSound: true })
  }

  function markRead(id: string): void {
    const idx = items.value.findIndex((row) => row.id === id)
    if (idx < 0 || items.value[idx].read) return
    items.value[idx] = { ...items.value[idx], read: true }
    persist()
  }

  function markAllRead(): void {
    if (!items.value.some((row) => !row.read)) return
    items.value = items.value.map((row) => (row.read ? row : { ...row, read: true }))
    persist()
  }

  async function ensureConnected(): Promise<void> {
    loadForCurrentUser()
    if (connected.value) return
    connected.value = true
    try {
      const { getNotificationSettings } = await import('@/features/notifications/api')
      const settings = await getNotificationSettings()
      setMutePhrases(settings.mute_phrases || [])
    } catch {
      // Mute phrases stay from local cache if settings API is unavailable.
    }
    await ensureGroupDirectory()
    await connectRealtime()
    for (const topic of FEED_TOPICS) {
      unsubscribers.push(
        getRealtimeWS().onTopic(topic, (payload) => {
          push(topic, payload)
        }),
      )
    }
  }

  function teardown(): void {
    unsubscribers.forEach((fn) => fn())
    unsubscribers = []
    connected.value = false
  }

  return {
    items,
    mutePhrases,
    unreadCount,
    loadForCurrentUser,
    setMutePhrases,
    push,
    pushInbound,
    markRead,
    markAllRead,
    ensureConnected,
    teardown,
  }
})
