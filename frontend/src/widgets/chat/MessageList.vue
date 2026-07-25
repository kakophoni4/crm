<script setup lang="ts">
import { NEmpty, NSpin, NTag } from 'naive-ui'
import { format } from 'date-fns'
import { ru } from 'date-fns/locale'
import { Reply } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { ChatMessage } from '@/entities/chat/types'
import ContactAvatar from '@/shared/ui/ContactAvatar.vue'
import { useAuthStore } from '@/shared/store/auth'
import MessageAttachment from '@/widgets/chat/MessageAttachment.vue'
import OptAttachmentBar from '@/widgets/chat/OptAttachmentBar.vue'
import { isAttachmentPlaceholderText } from '@/features/chats/message-preview'

const props = defineProps<{
  messages: ChatMessage[]
  loading?: boolean
  loadingOlder?: boolean
  hasMore?: boolean
  chatId?: number | null
  contactId?: number | null
  contactName?: string | null
  /** Shown on outbound bubbles when sender nick is unknown (e.g. Telegram bot sync). */
  fallbackOutboundNick?: string | null
}>()

const emit = defineEmits<{
  loadOlder: []
  reply: [message: ChatMessage]
}>()

const auth = useAuthStore()
const viewportRef = ref<HTMLElement | null>(null)
const itemsRef = ref<HTMLElement | null>(null)
const stickToBottom = ref(true)
const loadingOlderGuard = ref(false)
const anchorHeight = ref<number | null>(null)
const scrollTopRef = ref(0)
const viewportHeightRef = ref(480)
/** Mutated in-place; heightsVersion invalidates virtual-range computeds. */
const measuredHeights = new Map<string, number>()
const heightsVersion = ref(0)
/** prefixOffsetsBuf[i] = sum of heights of items [0..i). Length = n+1. */
let prefixOffsetsBuf = new Float64Array(1)
/** Keys last synced into prefixOffsetsBuf (tip-append / skip detection). */
let prefixItemKeys: Array<string | number> = []

const OVERSCAN_ITEMS = 6
const DEFAULT_MESSAGE_HEIGHT = 68
const DEFAULT_DATE_HEIGHT = 32
/** Must match CSS margin-bottom on virtual rows (flex gap breaks spacer math). */
const ITEM_GAP_PX = 10
/** While reading history, block auto stick-to-bottom (resize/measure yank). */
const STICK_SUPPRESS_MS = 1500

let viewportResizeObserver: ResizeObserver | null = null
let itemResizeObserver: ResizeObserver | null = null
const observedItemElements = new Map<number, HTMLElement>()

/** Coalesce ResizeObserver measures into one heights update per frame. */
const pendingMeasures = new Map<string, { key: string; index: number; height: number }>()
let measureRafId = 0
let pendingStickToBottom = false
/** Timestamp until which scrollToBottom is ignored after user scrolls up. */
let stickSuppressedUntil = 0

function suppressStickToBottom(ms = STICK_SUPPRESS_MS): void {
  stickSuppressedUntil = Date.now() + ms
  stickToBottom.value = false
  pendingStickToBottom = false
}

function isStickAllowed(): boolean {
  return (
    stickToBottom.value &&
    Date.now() >= stickSuppressedUntil &&
    !loadingOlderGuard.value &&
    anchorHeight.value == null
  )
}

interface VirtualListItem {
  kind: 'date' | 'message'
  key: string | number
  msg?: ChatMessage
  msgIndex?: number
  dateLabel?: string
}

function messageKey(msg: ChatMessage | undefined): string | number | null {
  if (!msg) return null
  return msg._clientKey ?? msg.id
}

const sorted = computed(() => {
  const msgs = props.messages
  if (msgs.length <= 1) return msgs
  // Store keeps chronological order; avoid O(n log n) + copy on every WS tick.
  let ordered = true
  for (let i = 1; i < msgs.length; i += 1) {
    const prev = msgs[i - 1]
    const next = msgs[i]
    if (
      prev.created_at > next.created_at ||
      (prev.created_at === next.created_at && prev.id > next.id)
    ) {
      ordered = false
      break
    }
  }
  if (ordered) return msgs
  return [...msgs].sort((a, b) => {
    if (a.created_at !== b.created_at) {
      return a.created_at < b.created_at ? -1 : 1
    }
    return a.id - b.id
  })
})

const messagesById = computed(() => {
  const map = new Map<number, ChatMessage>()
  for (const msg of sorted.value) {
    if (msg.id > 0) map.set(msg.id, msg)
  }
  return map
})

const listItems = computed((): VirtualListItem[] => {
  const items: VirtualListItem[] = []
  const msgs = sorted.value
  for (let i = 0; i < msgs.length; i += 1) {
    const msg = msgs[i]
    if (shouldShowDateSeparator(i)) {
      items.push({
        kind: 'date',
        key: `d:${messageKey(msg)}`,
        dateLabel: formatDateSeparator(msg.created_at),
      })
    }
    items.push({
      kind: 'message',
      key: messageKey(msg)!,
      msg,
      msgIndex: i,
    })
  }
  return items
})

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

function senderNick(msg: ChatMessage): string | null {
  if (msg.direction !== 'outbound') return null
  const fromApi =
    msg.sender_username?.trim()
    || msg.author_username?.trim()
    || msg.author_full_name?.trim()
  if (fromApi) return fromApi
  if (msg.sender_user_id != null && msg.sender_user_id === auth.user?.id) {
    return auth.user.username?.trim() || auth.user.full_name?.trim() || null
  }
  return props.fallbackOutboundNick?.trim() || null
}

function replyPreview(msg: ChatMessage): string {
  const text = msg.text?.trim()
  if (text) return text
  if (msg.attachments?.length) return 'Вложение'
  return `Сообщение №${msg.id}`
}

function quotedMessage(msg: ChatMessage): ChatMessage | null {
  if (msg.reply_to_message_id == null) return null
  return messagesById.value.get(msg.reply_to_message_id) ?? null
}

function shouldShowMessageText(msg: ChatMessage): boolean {
  const text = msg.text?.trim()
  if (!text) return false
  if (isAttachmentPlaceholderText(text)) return false
  const att = msg.attachments?.[0] as { filename?: string; name?: string } | undefined
  if (!att) return true
  const fn = (att.filename ?? att.name)?.trim()
  return !fn || text !== fn
}

function heightCacheKey(item: VirtualListItem): string {
  return String(item.key)
}

function estimateItemHeight(item: VirtualListItem): number {
  if (item.kind === 'date') return DEFAULT_DATE_HEIGHT
  const msg = item.msg!
  let h = 44
  const text = msg.text?.trim()
  if (text && shouldShowMessageText(msg)) {
    h += Math.min(320, Math.ceil(text.length / 36) * 20)
  }
  if (quotedMessage(msg)) h += 34
  if (msg.attachments?.length) h += 72 * msg.attachments.length
  return Math.max(h, msg.direction === 'inbound' ? 36 : 28)
}

function resolvedItemHeight(item: VirtualListItem): number {
  const base = measuredHeights.get(heightCacheKey(item)) ?? estimateItemHeight(item)
  // Trailing gap after every row keeps prefix offsets aligned with laid-out margins.
  return base + ITEM_GAP_PX
}

function rememberPrefixItemKeys(items: VirtualListItem[]): void {
  const n = items.length
  const keys = new Array<string | number>(n)
  for (let i = 0; i < n; i += 1) keys[i] = items[i].key
  prefixItemKeys = keys
}

function rebuildPrefixOffsets(items: VirtualListItem[]): void {
  const n = items.length
  if (prefixOffsetsBuf.length !== n + 1) {
    prefixOffsetsBuf = new Float64Array(n + 1)
  }
  prefixOffsetsBuf[0] = 0
  for (let i = 0; i < n; i += 1) {
    prefixOffsetsBuf[i + 1] = prefixOffsetsBuf[i] + resolvedItemHeight(items[i])
  }
  rememberPrefixItemKeys(items)
  heightsVersion.value += 1
}

/** Tip-append: keep existing prefix sums, extend buffer for new tail only. */
function extendPrefixOffsetsForAppend(items: VirtualListItem[], fromIndex: number): void {
  const n = items.length
  if (prefixOffsetsBuf.length !== n + 1) {
    const next = new Float64Array(n + 1)
    next.set(prefixOffsetsBuf)
    prefixOffsetsBuf = next
  }
  for (let i = fromIndex; i < n; i += 1) {
    prefixOffsetsBuf[i + 1] = prefixOffsetsBuf[i] + resolvedItemHeight(items[i])
  }
  const keys = prefixItemKeys
  keys.length = n
  for (let i = fromIndex; i < n; i += 1) {
    keys[i] = items[i].key
  }
  heightsVersion.value += 1
}

function applyHeightDeltaAt(index: number, delta: number): void {
  if (delta === 0) return
  const buf = prefixOffsetsBuf
  // Item top is unchanged; growth shifts everything below. Keep visual anchor stable
  // when the changed row is above (or at) the current scroll position.
  const itemTop = buf[index] ?? 0
  for (let j = index + 1; j < buf.length; j += 1) {
    buf[j] += delta
  }
  const el = viewportRef.value
  if (el && scrollTopRef.value > itemTop) {
    el.scrollTop += delta
    scrollTopRef.value = el.scrollTop
  }
}

function prefixKeysMatchPrefix(items: VirtualListItem[], count: number): boolean {
  const keys = prefixItemKeys
  if (keys.length < count) return false
  for (let i = 0; i < count; i += 1) {
    if (items[i].key !== keys[i]) return false
  }
  return true
}

/**
 * Incremental prefix sync when possible:
 * - same keys → no-op (height deltas come from measures)
 * - tip append → extend Float64Array + append tail sums
 * - prepend / shrink / reorder / chat reset → full rebuild
 */
function syncPrefixOffsets(items: VirtualListItem[]): void {
  const n = items.length
  const prevN = prefixItemKeys.length

  if (n === prevN && prevN > 0 && prefixOffsetsBuf.length === prevN + 1) {
    if (prefixKeysMatchPrefix(items, prevN)) return
  }

  if (
    n > prevN &&
    prevN > 0 &&
    prefixOffsetsBuf.length === prevN + 1 &&
    prefixKeysMatchPrefix(items, prevN)
  ) {
    extendPrefixOffsetsForAppend(items, prevN)
    return
  }

  rebuildPrefixOffsets(items)
}

/** Virtual-range computeds depend on heightsVersion; buffer is mutated in place. */
const prefixOffsets = computed(() => {
  void heightsVersion.value
  return prefixOffsetsBuf
})

watch(listItems, (items) => syncPrefixOffsets(items), { immediate: true })

const totalListHeight = computed(() => {
  const offsets = prefixOffsets.value
  return offsets[offsets.length - 1] ?? 0
})

function findIndexAtOffset(offset: number): number {
  const offsets = prefixOffsets.value
  const len = listItems.value.length
  if (!len) return 0
  let lo = 0
  let hi = len
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (offsets[mid + 1] <= offset) lo = mid + 1
    else hi = mid
  }
  return lo
}

const visibleRange = computed(() => {
  const items = listItems.value
  const len = items.length
  if (!len) return { start: 0, end: 0 }

  const scrollTop = scrollTopRef.value
  const viewH = viewportHeightRef.value
  const overscanPx = OVERSCAN_ITEMS * DEFAULT_MESSAGE_HEIGHT

  const rawStart = findIndexAtOffset(Math.max(0, scrollTop - overscanPx))
  const rawEnd = findIndexAtOffset(scrollTop + viewH + overscanPx)
  const start = Math.max(0, rawStart - OVERSCAN_ITEMS)
  const end = Math.min(len, rawEnd + OVERSCAN_ITEMS + 1)
  return { start, end }
})

const visibleItems = computed(() => {
  const { start, end } = visibleRange.value
  return listItems.value.slice(start, end).map((item, i) => ({
    item,
    index: start + i,
  }))
})

/** Viewport CSS padding (top+bottom); pin math uses the content box. */
const VIEWPORT_PAD_Y = 24

const topSpacerHeight = computed(() => {
  const { start } = visibleRange.value
  const virtualTop = prefixOffsets.value[start] ?? 0
  // Mid/long thread: only the virtual window offset.
  if (start > 0) return virtualTop

  const total = totalListHeight.value
  const viewH = viewportHeightRef.value
  const avail = Math.max(0, viewH - VIEWPORT_PAD_Y)
  // Short thread: pad above so the last messages sit on the composer (Telegram-style).
  // CSS flex-end/min-height under NSpin is unreliable and left a blank hole instead.
  if (total > 0 && avail > 0 && total < avail) {
    return avail - total
  }
  return virtualTop
})

const bottomSpacerHeight = computed(() => {
  const { end } = visibleRange.value
  const total = totalListHeight.value
  return Math.max(0, total - (prefixOffsets.value[end] ?? total))
})

const virtualPaddingStyle = computed(() => ({
  paddingTop: `${topSpacerHeight.value}px`,
  paddingBottom: `${bottomSpacerHeight.value}px`,
}))

function scheduleMeasureFlush(): void {
  if (measureRafId) return
  measureRafId = requestAnimationFrame(flushMeasuredHeights)
}

function queueMeasuredHeight(index: number, item: VirtualListItem, height: number): void {
  const key = heightCacheKey(item)
  const rounded = Math.ceil(height)
  if (measuredHeights.get(key) === rounded) {
    const pending = pendingMeasures.get(key)
    if (!pending || pending.height === rounded) return
  }
  pendingMeasures.set(key, { key, index, height: rounded })
  scheduleMeasureFlush()
}

function flushMeasuredHeights(): void {
  measureRafId = 0
  const items = listItems.value
  let deltaApplied = false
  let needRebuild = false

  for (const { key, index, height } of pendingMeasures.values()) {
    if (measuredHeights.get(key) === height) continue
    const item = items[index]
    if (!item || heightCacheKey(item) !== key) {
      measuredHeights.set(key, height)
      needRebuild = true
      continue
    }
    const prevMeasured = measuredHeights.get(key)
    const oldBase = prevMeasured ?? estimateItemHeight(item)
    measuredHeights.set(key, height)
    const delta = height - oldBase
    if (delta !== 0) {
      applyHeightDeltaAt(index, delta)
      deltaApplied = true
    }
  }
  pendingMeasures.clear()

  if (needRebuild) {
    rebuildPrefixOffsets(items)
  } else if (deltaApplied) {
    heightsVersion.value += 1
  }

  const stick = pendingStickToBottom
  pendingStickToBottom = false
  if (stick && isStickAllowed()) {
    scrollToBottom()
  }
}

function cancelPendingMeasures(): void {
  if (measureRafId) {
    cancelAnimationFrame(measureRafId)
    measureRafId = 0
  }
  pendingMeasures.clear()
  pendingStickToBottom = false
}

function onItemResize(entry: ResizeObserverEntry): void {
  const el = entry.target as HTMLElement
  const index = Number(el.dataset.vindex)
  if (!Number.isFinite(index)) return
  const item = listItems.value[index]
  if (!item) return
  const height = el.offsetHeight
  if (height <= 0) return
  queueMeasuredHeight(index, item, height)
  if (isStickAllowed()) {
    pendingStickToBottom = true
    scheduleMeasureFlush()
  }
}

function bindItemResizeObserver(): void {
  itemResizeObserver?.disconnect()
  itemResizeObserver = null
  observedItemElements.clear()
  if (typeof ResizeObserver === 'undefined') return
  itemResizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) onItemResize(entry)
  })
}

function bindVirtualItemRef(el: Element | { $el?: Element } | null, index: number): void {
  const prev = observedItemElements.get(index)
  if (prev && itemResizeObserver) itemResizeObserver.unobserve(prev)
  observedItemElements.delete(index)

  const node =
    el instanceof HTMLElement
      ? el
      : el && '$el' in el && el.$el instanceof HTMLElement
        ? el.$el
        : null
  if (!node || !itemResizeObserver) return

  node.dataset.vindex = String(index)
  observedItemElements.set(index, node)
  itemResizeObserver.observe(node)
}

function scrollToBottom(): void {
  if (!isStickAllowed()) return
  const el = viewportRef.value
  if (!el) return
  // Instant jump — smooth scroll often undershoots when height is still growing.
  el.scrollTop = el.scrollHeight
  scrollTopRef.value = el.scrollTop
}

async function scrollToBottomAfterLayout(): Promise<void> {
  await nextTick()
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  if (!isStickAllowed()) return
  scrollToBottom()
  // Attachments/images often bump height after the first paint.
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
  if (isStickAllowed()) scrollToBottom()
}

function bindViewportResizeObserver(): void {
  viewportResizeObserver?.disconnect()
  viewportResizeObserver = null
  const el = viewportRef.value
  if (!el || typeof ResizeObserver === 'undefined') return
  viewportHeightRef.value = el.clientHeight
  viewportResizeObserver = new ResizeObserver(() => {
    viewportHeightRef.value = el.clientHeight
  })
  viewportResizeObserver.observe(el)
}

onMounted(() => {
  // Remounted per chat (`:key="chatId"`) with messages already filled — watches may not fire.
  stickSuppressedUntil = 0
  stickToBottom.value = true
  bindItemResizeObserver()
  bindViewportResizeObserver()
  void scrollToBottomAfterLayout()
})

onBeforeUnmount(() => {
  cancelPendingMeasures()
  viewportResizeObserver?.disconnect()
  viewportResizeObserver = null
  itemResizeObserver?.disconnect()
  itemResizeObserver = null
  observedItemElements.clear()
})

function onViewportScroll(): void {
  const el = viewportRef.value
  if (!el) return
  const prevTop = scrollTopRef.value
  scrollTopRef.value = el.scrollTop
  const distance = el.scrollHeight - el.scrollTop - el.clientHeight

  // Upward scroll: lock stick so virtualization measure/resize cannot yank back down.
  if (el.scrollTop + 1 < prevTop) {
    suppressStickToBottom()
  } else if (Date.now() >= stickSuppressedUntil) {
    stickToBottom.value = distance < 72
  }

  if (
    el.scrollTop < 96 &&
    props.hasMore &&
    !props.loadingOlder &&
    !loadingOlderGuard.value
  ) {
    loadingOlderGuard.value = true
    suppressStickToBottom()
    anchorHeight.value = el.scrollHeight
    emit('loadOlder')
  }
}

watch(
  () => props.loadingOlder,
  async (loading, wasLoading) => {
    if (!loading) {
      loadingOlderGuard.value = false
    }
    if (wasLoading && !loading && anchorHeight.value != null) {
      await nextTick()
      const el = viewportRef.value
      if (el) {
        el.scrollTop += el.scrollHeight - anchorHeight.value
        scrollTopRef.value = el.scrollTop
      }
      anchorHeight.value = null
    }
  },
)

watch(
  () => props.chatId,
  () => {
    stickSuppressedUntil = 0
    stickToBottom.value = true
    loadingOlderGuard.value = false
    anchorHeight.value = null
    cancelPendingMeasures()
    measuredHeights.clear()
    rebuildPrefixOffsets(listItems.value)
    scrollTopRef.value = 0
    void scrollToBottomAfterLayout()
  },
)

watch(
  () => props.loading,
  (loading, wasLoading) => {
    if (wasLoading && !loading && isStickAllowed()) {
      void scrollToBottomAfterLayout()
    }
  },
)

// Tip/length only — deep watch on every attachment status tick was a major lag source.
watch(
  () => {
    const msgs = props.messages
    const last = msgs[msgs.length - 1]
    const first = msgs[0]
    return [msgs.length, messageKey(last), messageKey(first)] as const
  },
  (next, prev) => {
    if (!isStickAllowed()) return
    if (!next[0]) return

    const [nextLen, nextLastKey, nextFirstKey] = next
    const prevLen = prev?.[0] ?? 0
    const prevLastKey = prev?.[1] ?? null
    const prevFirstKey = prev?.[2] ?? null
    const isPrepend =
      prevLen > 0 &&
      nextLen > prevLen &&
      prevFirstKey !== nextFirstKey &&
      prevLastKey === nextLastKey
    if (isPrepend) return

    const lengthChanged = prevLen !== nextLen
    const tipChanged = prevLastKey !== nextLastKey
    if (prev != null && !lengthChanged && !tipChanged) return

    void scrollToBottomAfterLayout()
  },
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
        <div ref="itemsRef" class="message-list__items" :style="virtualPaddingStyle">
          <template v-for="{ item, index } in visibleItems" :key="item.key">
            <div
              v-if="item.kind === 'date'"
              :ref="(el) => bindVirtualItemRef(el, index)"
              class="message-list__date-separator"
            >
              {{ item.dateLabel }}
            </div>
            <div
              v-else
              :ref="(el) => bindVirtualItemRef(el, index)"
              class="message-list__row"
              :class="{
                'message-list__row--out': item.msg!.direction === 'outbound',
                'message-list__row--failed': item.msg!._failed,
              }"
            >
              <ContactAvatar
                v-if="item.msg!.direction === 'inbound' && contactId != null && contactName"
                class="message-list__avatar"
                :contact-id="contactId"
                :full-name="contactName"
                :size="28"
              />
              <div
                class="message-list__bubble"
                :class="
                  item.msg!.direction === 'outbound'
                    ? 'message-list__bubble--out'
                    : 'message-list__bubble--in'
                "
              >
                <div v-if="quotedMessage(item.msg!)" class="message-list__quote">
                  {{ replyPreview(quotedMessage(item.msg!)!) }}
                </div>
                <p v-if="shouldShowMessageText(item.msg!)" class="message-list__text">
                  {{ item.msg!.text }}
                </p>
                <div v-if="item.msg!.attachments?.length" class="message-list__attachments">
                  <template v-for="(att, i) in item.msg!.attachments" :key="i">
                    <MessageAttachment
                      :att="att"
                      :eager="(item.msgIndex ?? 0) >= sorted.length - 8"
                    />
                    <OptAttachmentBar
                      v-if="item.msg!.direction === 'inbound'"
                      :chat-id="chatId"
                      :message-id="item.msg!.id"
                      :attachment-index="i"
                      :attachment="att"
                    />
                  </template>
                </div>
                <footer class="message-list__meta">
                  <span :title="formatFullDateTime(item.msg!.created_at)">
                    {{ formatTime(item.msg!.created_at) }}
                  </span>
                  <span v-if="senderNick(item.msg!)" class="message-list__sender">
                    {{ senderNick(item.msg!) }}
                  </span>
                  <NTag v-if="item.msg!._optimistic" size="tiny" :bordered="false">отправка...</NTag>
                  <NTag v-if="item.msg!._failed" size="tiny" type="error" :bordered="false">ошибка</NTag>
                </footer>
              </div>
              <button
                type="button"
                class="message-list__reply"
                title="Ответить"
                aria-label="Ответить"
                @click="emit('reply', item.msg!)"
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

.message-list__viewport :deep(.n-spin-container),
.message-list__viewport :deep(.n-spin-content) {
  display: block;
  min-height: 0;
}

.message-list__items {
  display: flex;
  flex-direction: column;
  width: 100%;
  box-sizing: border-box;
}

.message-list__older-hint {
  align-self: center;
  margin-bottom: 8px;
  font-size: 0.8rem;
  color: var(--app-text-muted);
}

.message-list__date-separator {
  align-self: center;
  margin-bottom: 10px;
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
  margin-bottom: 10px;
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
  border-color: color-mix(in srgb, var(--app-accent) 28%, var(--app-border));
}

.message-list__bubble--in {
  border-color: var(--app-border);
}

.message-list__row--failed .message-list__bubble {
  border-color: var(--app-danger);
  box-shadow: 0 0 0 1px rgba(208, 48, 80, 0.35);
}

.message-list__sender {
  font-size: 0.7rem;
  opacity: 0.85;
}

.message-list__quote {
  margin-bottom: 6px;
  padding: 5px 8px;
  border-left: 3px solid var(--app-accent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--app-accent) 10%, transparent);
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
  color: var(--app-accent);
  border-color: var(--app-accent);
}

.message-list__attachments {
  font-size: 0.85rem;
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  max-width: 100%;
  min-width: 0;
}

.message-list__empty {
  padding: 48px 0;
}
</style>
