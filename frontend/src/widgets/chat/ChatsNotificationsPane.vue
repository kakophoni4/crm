<script setup lang="ts">
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import { NButton, NEmpty, NSpace } from 'naive-ui'
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'

import { useChatNotificationsStore } from '@/features/chats/notifications-store'

withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })

const router = useRouter()
const notifications = useChatNotificationsStore()

function timeLabel(ts: number): string {
  return format(ts, 'HH:mm', { locale: ru })
}

function onOpen(id: string, chatId: number | null): void {
  notifications.markRead(id)
  if (chatId != null) {
    void router.push({ name: 'chats', query: { chatId: String(chatId) } })
  }
}

onMounted(() => {
  void notifications.ensureConnected()
})

onUnmounted(() => {
  // Подписка общая на store — не рвём при размонтировании панели.
})
</script>

<template>
  <div
    class="chats-notifications-pane"
    :class="{ 'chats-notifications-pane--embedded': embedded }"
  >
    <div class="chats-notifications-pane__head">
      <strong v-if="!embedded" class="chats-notifications-pane__title">Уведомления</strong>
      <div class="chats-notifications-pane__actions">
        <span v-if="notifications.unreadCount" class="chats-notifications-pane__unread-count">
          непрочитано: {{ notifications.unreadCount }}
        </span>
        <NButton
          v-if="notifications.unreadCount"
          size="tiny"
          quaternary
          @click="notifications.markAllRead()"
        >
          Прочитать все
        </NButton>
      </div>
    </div>

    <NEmpty
      v-if="!notifications.items.length"
      description="Пока тихо — события появятся здесь."
    />
    <NSpace v-else vertical :size="8" class="chats-notifications-pane__feed">
      <button
        v-for="row in notifications.items"
        :key="row.id"
        type="button"
        class="chats-notifications-pane__row"
        :class="{
          'chats-notifications-pane__row--click': row.chatId != null,
          'chats-notifications-pane__row--unread': !row.read,
          'chats-notifications-pane__row--read': row.read,
        }"
        @click="onOpen(row.id, row.chatId)"
      >
        <span class="chats-notifications-pane__time">{{ timeLabel(row.at) }}</span>
        <span class="chats-notifications-pane__line">{{ row.line }}</span>
        <span class="chats-notifications-pane__status">
          {{ row.read ? 'прочитано' : 'новое' }}
        </span>
      </button>
    </NSpace>
  </div>
</template>

<style scoped>
.chats-notifications-pane__head {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
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

.chats-notifications-pane--embedded {
  flex: 1;
  padding: 8px 12px 12px;
  border: none;
  border-radius: 0;
  background: transparent;
}

.chats-notifications-pane__title {
  font-size: 0.9375rem;
}

.chats-notifications-pane__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.chats-notifications-pane__unread-count {
  font-size: 0.75rem;
  color: var(--app-text-muted);
}

.chats-notifications-pane__feed {
  width: 100%;
  max-height: min(52vh, 420px);
  overflow-y: auto;
  padding-right: 2px;
}

.chats-notifications-pane__row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 10px;
  align-items: flex-start;
  width: 100%;
  margin: 0;
  padding: 8px 10px;
  text-align: left;
  font: inherit;
  color: inherit;
  background: var(--app-surface-elevated);
  border: 1px solid var(--app-border);
  border-radius: 8px;
  cursor: pointer;
  box-sizing: border-box;
}

.chats-notifications-pane__row--unread {
  border-left: 3px solid var(--app-accent);
  background: color-mix(in srgb, var(--app-accent) 8%, var(--app-surface-elevated));
}

.chats-notifications-pane__row--read {
  opacity: 0.72;
}

.chats-notifications-pane__row:hover {
  background: color-mix(in srgb, var(--app-text) 7%, var(--app-surface-elevated));
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

.chats-notifications-pane__row--unread .chats-notifications-pane__line {
  font-weight: 600;
}

.chats-notifications-pane__status {
  flex-shrink: 0;
  font-size: 0.7rem;
  opacity: 0.65;
  white-space: nowrap;
}
</style>
