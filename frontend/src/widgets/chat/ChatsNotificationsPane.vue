<script setup lang="ts">
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import { NEmpty, NSpace, NTabPane, NTabs } from 'naive-ui'
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import TransferInboxPanel from '@/features/contacts/transfer-card/TransferInboxPanel.vue'
import { ensureGroupDirectory, lookupGroupName } from '@/features/groups/directory'
import { playTransferInboxSound } from '@/shared/audio/transfer-inbox'
import { connectRealtime, getRealtimeWS } from '@/shared/realtime/ws-client'

type FeedTopic =
  | 'message.replied.on_behalf'
  | 'contact.escalation.group_notify'
  | 'contact.escalation.owner_notify'
  | 'contact.ownership.assigned'
  | 'contact.ownership.reassigned'
  | 'contact.ownership.transferred'

type FeedItem = {
  id: string
  at: number
  topic: FeedTopic
  line: string
  chatId: number | null
}

const FEED_TOPICS: FeedTopic[] = [
  'message.replied.on_behalf',
  'contact.escalation.group_notify',
  'contact.escalation.owner_notify',
  'contact.ownership.assigned',
  'contact.ownership.reassigned',
  'contact.ownership.transferred',
]

const router = useRouter()
const feed = ref<FeedItem[]>([])
const MAX_ITEMS = 50
const recentDedupe = new Map<string, number>()

let unsubscribers: (() => void)[] = []

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
  const name = str(payload, 'contact_full_name')
  if (name) return `«${name}»`
  const id = num(payload, 'contact_id')
  return id != null ? `контакт #${id}` : 'карточка'
}

function groupSuffix(payload: Record<string, unknown>): string {
  const name =
    str(payload, 'group_name') ?? lookupGroupName(num(payload, 'group_id'))
  if (name) return ` · ${name}`
  return ''
}

function dedupeKey(topic: FeedTopic, payload: Record<string, unknown>): string {
  const perspective = str(payload, 'perspective') ?? ''
  return `${topic}:${num(payload, 'contact_id') ?? ''}:${num(payload, 'group_id') ?? ''}:${perspective}`
}

function isDuplicate(key: string): boolean {
  const now = Date.now()
  const prev = recentDedupe.get(key)
  recentDedupe.set(key, now)
  if (prev != null && now - prev < 900) {
    return true
  }
  if (recentDedupe.size > 200) {
    for (const [k, t] of recentDedupe) {
      if (now - t > 60_000) recentDedupe.delete(k)
    }
  }
  return false
}

function formatLine(topic: FeedTopic, payload: Record<string, unknown>): string {
  const contact = contactLabel(payload)
  const group = groupSuffix(payload)

  switch (topic) {
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

function pushFeed(topic: FeedTopic, payload: Record<string, unknown>): void {
  const chatId = num(payload, 'chat_id')
  const line = formatLine(topic, payload)
  const id = `${topic}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  feed.value = [{ id, at: Date.now(), topic, line, chatId }, ...feed.value].slice(0, MAX_ITEMS)
}

function onFeedTopic(topic: FeedTopic, payload: Record<string, unknown>): void {
  const key = dedupeKey(topic, payload)
  if (isDuplicate(key)) return
  void playTransferInboxSound()
  pushFeed(topic, payload)
}

function openChat(chatId: number): void {
  void router.push({ name: 'chats', query: { chatId: String(chatId) } })
}

function timeLabel(ts: number): string {
  return format(ts, 'HH:mm', { locale: ru })
}

onMounted(async () => {
  await ensureGroupDirectory()
  await connectRealtime()
  for (const topic of FEED_TOPICS) {
    unsubscribers.push(
      getRealtimeWS().onTopic(topic, (payload) => {
        onFeedTopic(topic, payload)
      }),
    )
  }
})

onUnmounted(() => {
  unsubscribers.forEach((fn) => fn())
  unsubscribers = []
})
</script>

<template>
  <div class="chats-notifications-pane">
    <div class="chats-notifications-pane__head">
      <strong class="chats-notifications-pane__title">Уведомления</strong>
    </div>

    <NTabs type="line" size="small" animated class="chats-notifications-pane__tabs">
      <NTabPane name="transfers" tab="Передачи">
        <TransferInboxPanel embedded />
      </NTabPane>
      <NTabPane name="activity" tab="События">
        <NEmpty v-if="!feed.length" description="Пока тихо — события появятся здесь." />
        <NSpace v-else vertical :size="8" class="chats-notifications-pane__feed">
          <button
            v-for="row in feed"
            :key="row.id"
            type="button"
            class="chats-notifications-pane__row"
            :class="{ 'chats-notifications-pane__row--click': row.chatId != null }"
            @click="row.chatId != null && openChat(row.chatId)"
          >
            <span class="chats-notifications-pane__time">{{ timeLabel(row.at) }}</span>
            <span class="chats-notifications-pane__line">{{ row.line }}</span>
          </button>
        </NSpace>
      </NTabPane>
    </NTabs>
  </div>
</template>

<style scoped>
.chats-notifications-pane__head {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
}

.chats-notifications-pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 14px 14px 12px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  background: var(--app-surface);
  box-sizing: border-box;
}

.chats-notifications-pane__title {
  font-size: 0.9375rem;
}

.chats-notifications-pane :deep(.n-card) {
  background: transparent;
}

.chats-notifications-pane :deep(.n-card.n-card--embedded) {
  border: none;
  box-shadow: none;
}

.chats-notifications-pane__tabs {
  margin-top: 4px;
}

.chats-notifications-pane__feed {
  width: 100%;
  max-height: min(52vh, 420px);
  overflow-y: auto;
  padding-right: 2px;
}

.chats-notifications-pane__row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  width: 100%;
  margin: 0;
  padding: 8px 10px;
  text-align: left;
  font: inherit;
  color: inherit;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  cursor: default;
  box-sizing: border-box;
}

.chats-notifications-pane__row--click {
  cursor: pointer;
}

.chats-notifications-pane__row--click:hover {
  background: rgba(255, 255, 255, 0.07);
}

.chats-notifications-pane__time {
  flex-shrink: 0;
  font-size: 0.75rem;
  opacity: 0.55;
  font-variant-numeric: tabular-nums;
  min-width: 2.5rem;
}

.chats-notifications-pane__line {
  font-size: 0.8125rem;
  line-height: 1.4;
}
</style>
