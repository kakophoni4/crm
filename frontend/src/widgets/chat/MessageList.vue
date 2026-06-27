<script setup lang="ts">
import { NEmpty, NSpin, NTag } from 'naive-ui'
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import { Reply } from 'lucide-vue-next'
import { computed, nextTick, ref, watch } from 'vue'

import type { ChatMessage } from '@/entities/chat/types'
import { formatOnBehalfLabel } from '@/entities/contact/on-behalf-label'
import ContactAvatar from '@/shared/ui/ContactAvatar.vue'
import MessageAttachment from '@/widgets/chat/MessageAttachment.vue'

const props = defineProps<{
  messages: ChatMessage[]
  loading?: boolean
  loadingOlder?: boolean
  hasMore?: boolean
  chatId?: number | null
  contactId?: number | null
  contactName?: string | null
}>()

const emit = defineEmits<{
  loadOlder: []
  reply: [message: ChatMessage]
}>()

const viewportRef = ref<HTMLElement | null>(null)
const stickToBottom = ref(true)
const loadingOlderGuard = ref(false)
const anchorHeight = ref<number | null>(null)

const sorted = computed(() =>
  [...props.messages].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  ),
)

function formatTime(iso: string): string {
  try {
    return format(new Date(iso), 'HH:mm', { locale: ru })
  } catch {
    return ''
  }
}

function formatFullDateTime(iso: string): string {
  try {
    return format(new Date(iso), 'dd.MM.yyyy HH:mm', { locale: ru })
  } catch {
    return iso
  }
}

function formatDateSeparator(iso: string): string {
  try {
    return format(new Date(iso), 'd MMMM yyyy', { locale: ru })
  } catch {
    return ''
  }
}

function isSameDay(a: string, b: string): boolean {
  try {
    return format(new Date(a), 'yyyy-MM-dd') === format(new Date(b), 'yyyy-MM-dd')
  } catch {
    return false
  }
}

function shouldShowDateSeparator(index: number): boolean {
  const current = sorted.value[index]
  if (!current) return false
  const prev = sorted.value[index - 1]
  return !prev || !isSameDay(prev.created_at, current.created_at)
}

function onBehalfLabel(msg: ChatMessage): string | null {
  return formatOnBehalfLabel(msg)
}

function replyPreview(msg: ChatMessage): string {
  const text = msg.text?.trim()
  if (text) return text
  if (msg.attachments?.length) return 'Вложение'
  return `Сообщение №${msg.id}`
}

function quotedMessage(msg: ChatMessage): ChatMessage | null {
  if (msg.reply_to_message_id == null) return null
  return sorted.value.find((item) => item.id === msg.reply_to_message_id) ?? null
}

function shouldShowMessageText(msg: ChatMessage): boolean {
  const text = msg.text?.trim()
  if (!text) return false
  const att = msg.attachments?.[0] as { filename?: string; name?: string } | undefined
  if (!att) return true
  const fn = (att.filename ?? att.name)?.trim()
  return !fn || text !== fn
}

function scrollToBottom(smooth = false): void {
  const el = viewportRef.value
  if (!el) return
  el.scrollTo({
    top: el.scrollHeight,
    behavior: smooth ? 'smooth' : 'auto',
  })
}

function onViewportScroll(): void {
  const el = viewportRef.value
  if (!el) return
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight
  stickToBottom.value = distance < 72

  if (
    el.scrollTop < 96 &&
    props.hasMore &&
    !props.loadingOlder &&
    !loadingOlderGuard.value
  ) {
    loadingOlderGuard.value = true
    stickToBottom.value = false
    anchorHeight.value = el.scrollHeight
    emit('loadOlder')
  }
}

watch(
  () => props.loadingOlder,
  async (loading, wasLoading) => {
    if (!loading) {
      loadingOlderGuard.value = false
      anchorHeight.value = null
    }
    if (wasLoading && !loading && anchorHeight.value != null) {
      await nextTick()
      const el = viewportRef.value
      if (el) {
        el.scrollTop += el.scrollHeight - anchorHeight.value
      }
      anchorHeight.value = null
    }
  },
)

watch(
  () => props.chatId,
  () => {
    stickToBottom.value = true
    loadingOlderGuard.value = false
    anchorHeight.value = null
    void nextTick(() => scrollToBottom(false))
  },
)

watch(
  () => props.loading,
  async (loading, wasLoading) => {
    if (wasLoading && !loading && stickToBottom.value) {
      await nextTick()
      scrollToBottom(false)
    }
  },
)

watch(
  () => props.messages,
  async (next, prev) => {
    if (!stickToBottom.value || next === prev) return
    const prevLast = prev?.[prev.length - 1]
    const nextLast = next[next.length - 1]
    if (!nextLast) return
    const isPrepend =
      prev != null &&
      prev.length > 0 &&
      next.length > prev.length &&
      prev[0]?.id !== next[0]?.id &&
      prevLast?.id === nextLast?.id
    if (isPrepend) return
    await nextTick()
    scrollToBottom(prev == null || next.length > prev.length)
  },
  { deep: true },
)
</script>

<template>
  <div class="message-list">
    <div ref="viewportRef" class="message-list__viewport" @scroll="onViewportScroll">
      <NSpin :show="loading && !sorted.length">
        <div v-if="loadingOlder" class="message-list__older-hint">Загрузка...</div>
        <div v-if="!sorted.length && !loading" class="message-list__empty">
          <NEmpty description="Сообщений пока нет" />
        </div>
        <div class="message-list__items">
          <template v-for="(msg, index) in sorted" :key="msg._clientKey ?? msg.id">
            <div v-if="shouldShowDateSeparator(index)" class="message-list__date-separator">
              {{ formatDateSeparator(msg.created_at) }}
            </div>
            <div
              class="message-list__row"
              :class="{
                'message-list__row--out': msg.direction === 'outbound',
                'message-list__row--failed': msg._failed,
              }"
            >
              <ContactAvatar
                v-if="msg.direction === 'inbound' && contactId != null && contactName"
                class="message-list__avatar"
                :contact-id="contactId"
                :full-name="contactName"
                :size="28"
              />
              <div
                class="message-list__bubble"
                :class="
                  msg.direction === 'outbound'
                    ? 'message-list__bubble--out'
                    : 'message-list__bubble--in'
                "
              >
                <NTag
                  v-if="msg.direction === 'outbound' && onBehalfLabel(msg)"
                  size="tiny"
                  type="info"
                  :bordered="false"
                  class="message-list__on-behalf"
                >
                  {{ onBehalfLabel(msg) }}
                </NTag>
                <div v-if="quotedMessage(msg)" class="message-list__quote">
                  {{ replyPreview(quotedMessage(msg)!) }}
                </div>
                <p v-if="shouldShowMessageText(msg)" class="message-list__text">{{ msg.text }}</p>
                <div v-if="msg.attachments?.length" class="message-list__attachments">
                  <MessageAttachment
                    v-for="(att, i) in msg.attachments"
                    :key="i"
                    :att="att"
                    eager
                  />
                </div>
                <footer class="message-list__meta">
                  <span :title="formatFullDateTime(msg.created_at)">
                    {{ formatTime(msg.created_at) }}
                  </span>
                  <NTag v-if="msg._optimistic" size="tiny" :bordered="false">отправка...</NTag>
                  <NTag v-if="msg._failed" size="tiny" type="error" :bordered="false">ошибка</NTag>
                </footer>
              </div>
              <button
                type="button"
                class="message-list__reply"
                title="Ответить"
                aria-label="Ответить"
                @click="emit('reply', msg)"
              >
                <Reply :size="14" />
              </button>
            </div>
          </template>
        </div>
      </NSpin>
    </div>
  </div>
</template>

<style scoped>
.message-list {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.message-list__viewport {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px 16px;
}

.message-list__viewport :deep(.n-spin-container) {
  display: flex;
  flex-direction: column;
  min-height: min-content;
}

.message-list__items {
  display: flex;
  flex-direction: column;
  width: 100%;
}

.message-list__items > .message-list__row:not(:last-child) {
  margin-bottom: 10px;
}

.message-list__older-hint {
  align-self: center;
  margin-bottom: 8px;
  font-size: 0.8rem;
  color: var(--app-text-muted);
}

.message-list__date-separator {
  align-self: center;
  margin: 10px 0;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--app-surface-elevated, #f4f4f5);
  color: var(--app-text-muted);
  font-size: 0.75rem;
}

.message-list__row {
  display: flex;
  flex-shrink: 0;
  align-items: flex-end;
  justify-content: flex-start;
  gap: 8px;
  width: 100%;
}

.message-list__row--out {
  justify-content: flex-end;
}

.message-list__row--out .message-list__avatar {
  display: none;
}

.message-list__row--out .message-list__reply {
  order: -1;
}

.message-list__avatar {
  align-self: flex-end;
}

.message-list__bubble {
  max-width: 72%;
  padding: 8px 12px;
  border-radius: 14px;
  border: 1px solid var(--app-border);
  background: var(--app-surface-elevated, #f4f4f5);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
  flex-shrink: 0;
}

.message-list__bubble--out {
  background: var(--app-accent-soft, #e8f3ff);
  border-color: color-mix(in srgb, var(--app-accent, #2080f0) 28%, var(--app-border));
}

.message-list__bubble--in {
  border-color: var(--app-border);
}

.message-list__row--failed .message-list__bubble {
  border-color: #d03050;
  box-shadow: 0 0 0 1px rgba(208, 48, 80, 0.35);
}

.message-list__on-behalf {
  margin-bottom: 4px;
  max-width: 100%;
  white-space: normal;
  height: auto;
}

.message-list__quote {
  margin-bottom: 6px;
  padding: 5px 8px;
  border-left: 3px solid var(--app-accent, #2080f0);
  border-radius: 6px;
  background: color-mix(in srgb, var(--app-accent, #2080f0) 10%, transparent);
  color: var(--app-text-muted);
  font-size: 0.8rem;
  line-height: 1.3;
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message-list__text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit, 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji', sans-serif;
}

.message-list__meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 0.75rem;
  opacity: 0.7;
}

.message-list__reply {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 1px solid var(--app-border);
  border-radius: 999px;
  background: var(--app-surface);
  color: var(--app-text-muted);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s, color 0.12s, border-color 0.12s;
}

.message-list__row:hover .message-list__reply,
.message-list__reply:focus-visible {
  opacity: 1;
}

.message-list__reply:hover {
  color: var(--app-accent, #2080f0);
  border-color: var(--app-accent, #2080f0);
}

.message-list__attachments {
  font-size: 0.85rem;
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.message-list__empty {
  padding: 48px 0;
}
</style>
