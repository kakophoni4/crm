<script setup lang="ts">
import { NButton, NUpload, useMessage } from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { MessageSquareText, FolderOpen, Paperclip, Plus, Send, Trash2, X } from 'lucide-vue-next'
import { computed, ref, nextTick, watch } from 'vue'

import {
  createQuickReply,
  hideQuickReply,
  listQuickReplies,
  trackQuickReplyUse,
  uploadFile,
  type QuickReplyTemplate,
} from '@/features/chats/api'
import type { ChatMessage } from '@/entities/chat/types'
import { formatFileSize, maxUploadBytesFor, uploadLimitLabel } from '@/shared/config/uploads'
import { isMessageSendShortcut } from '@/widgets/chat/message-input-hotkeys'
import EmojiPicker from '@/widgets/chat/EmojiPicker.vue'
import VaultFilePickerModal from '@/widgets/chat/VaultFilePickerModal.vue'

const props = defineProps<{
  disabled?: boolean
  placeholder?: string
  departmentId?: number | null
  groupId?: number | null
  chatId?: number | null
  replyTo?: ChatMessage | null
}>()

const emit = defineEmits<{
  send: [
    text: string,
    attachments: { file_id: number; name?: string; mime?: string }[],
    replyToMessageId: number | null,
  ]
  cancelReply: []
}>()

const message = useMessage()
const text = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const pendingFiles = ref<{ file_id: number; name: string; mime?: string }[]>([])
const sending = ref(false)
const dragOver = ref(false)
const quickReplies = ref<QuickReplyTemplate[]>([])
const quickRepliesOpen = ref(false)
const quickRepliesLoading = ref(false)
const creatingQuickReply = ref(false)
const newQuickReplyTitle = ref('')
const newQuickReplyBody = ref('')
const vaultPickerOpen = ref(false)
let quickReplySearchTimer: number | null = null

const quickReplyQuery = computed(() => text.value.trim())

const replyPreview = computed(() => {
  const msg = props.replyTo
  if (!msg) return ''
  const body = msg.text?.trim()
  if (body) return body
  if (msg.attachments?.length) return 'Вложение'
  return `Сообщение №${msg.id}`
})

function validateFileSize(file: File): boolean {
  const limit = maxUploadBytesFor(file)
  if (file.size <= limit) return true
  message.error(
    `Файл «${file.name}» слишком большой (макс. ${uploadLimitLabel(file)}, сейчас ${formatFileSize(file.size)})`,
  )
  return false
}

function onVaultFileSelect(file: { file_id: number; name: string; mime?: string }): void {
  pendingFiles.value.push({
    file_id: file.file_id,
    name: file.name,
    mime: file.mime,
  })
  message.success(`Файл «${file.name}» выбран из хранилища`)
}

function openVaultPicker(): void {
  if (props.disabled) return
  vaultPickerOpen.value = true
}

async function addFile(file: File): Promise<void> {
  if (props.disabled) return
  if (!validateFileSize(file)) return
  try {
    const uploaded = await uploadFile(file)
    pendingFiles.value.push({
      file_id: uploaded.id,
      name: uploaded.name ?? file.name,
      mime: uploaded.mime ?? file.type,
    })
    message.success(`Файл «${file.name}» загружен`)
  } catch (err) {
    message.error(err instanceof Error ? err.message : 'Не удалось загрузить файл')
  }
}

async function onBeforeUpload(data: { file: UploadFileInfo }): Promise<boolean> {
  const file = data.file.file
  if (!file) return false
  await addFile(file)
  return false
}

async function submit(): Promise<void> {
  const body = text.value.trim()
  if (!body && !pendingFiles.value.length) return
  if (props.disabled || sending.value) return
  sending.value = true
  try {
    emit(
      'send',
      body,
      pendingFiles.value.map((f) => ({
        file_id: f.file_id,
        name: f.name,
        mime: f.mime,
      })),
      props.replyTo?.id ?? null,
    )
    text.value = ''
    pendingFiles.value = []
    emit('cancelReply')
  } finally {
    sending.value = false
  }
}

function onKeydown(e: KeyboardEvent): void {
  if (isMessageSendShortcut(e)) {
    e.preventDefault()
    void submit()
  }
}

async function onPaste(e: ClipboardEvent): Promise<void> {
  if (props.disabled) return
  const items = e.clipboardData?.items
  if (!items?.length) return

  const imageFiles: File[] = []
  for (const item of items) {
    if (item.kind !== 'file') continue
    const file = item.getAsFile()
    if (!file) continue
    if (file.type.startsWith('image/') || item.type.startsWith('image/')) {
      imageFiles.push(file)
    }
  }

  if (!imageFiles.length) return
  e.preventDefault()
  for (const file of imageFiles) {
    await addFile(file)
  }
}

function onDragOver(e: DragEvent): void {
  e.preventDefault()
  if (props.disabled) return
  dragOver.value = true
}

function onDragLeave(e: DragEvent): void {
  e.preventDefault()
  dragOver.value = false
}

async function onDrop(e: DragEvent): Promise<void> {
  e.preventDefault()
  dragOver.value = false
  if (props.disabled) return
  const files = [...(e.dataTransfer?.files ?? [])]
  for (const file of files) {
    await addFile(file)
  }
}

function removePending(fileId: number): void {
  pendingFiles.value = pendingFiles.value.filter((f) => f.file_id !== fileId)
}

async function loadQuickReplies(): Promise<void> {
  if (props.disabled) return
  quickRepliesLoading.value = true
  try {
    quickReplies.value = await listQuickReplies({
      q: quickReplyQuery.value || undefined,
      department_id: props.groupId == null ? (props.departmentId ?? undefined) : undefined,
      group_id: props.groupId ?? undefined,
      limit: 8,
    })
  } catch {
    quickReplies.value = []
  } finally {
    quickRepliesLoading.value = false
  }
}

function scheduleQuickRepliesLoad(): void {
  if (!quickRepliesOpen.value) return
  if (quickReplySearchTimer != null) window.clearTimeout(quickReplySearchTimer)
  quickReplySearchTimer = window.setTimeout(() => {
    void loadQuickReplies()
  }, 180)
}

function openQuickReplies(): void {
  if (props.disabled) return
  quickRepliesOpen.value = true
  void loadQuickReplies()
}

async function applyQuickReply(template: QuickReplyTemplate): Promise<void> {
  text.value = template.body
  quickRepliesOpen.value = false
  void trackQuickReplyUse(template.id).catch(() => undefined)
  await nextTick()
  textareaRef.value?.focus()
}

function startCreateQuickReply(): void {
  creatingQuickReply.value = true
  newQuickReplyTitle.value = quickReplyQuery.value.slice(0, 80)
  newQuickReplyBody.value = text.value.trim()
}

async function saveQuickReply(): Promise<void> {
  const title = newQuickReplyTitle.value.trim()
  const body = newQuickReplyBody.value.trim()
  if (!title || !body) {
    message.warning('Заполните название и текст шаблона')
    return
  }
  try {
    await createQuickReply({
      title,
      body,
      department_id: props.groupId == null ? (props.departmentId ?? null) : null,
      group_id: props.groupId ?? null,
      is_active: true,
    })
    creatingQuickReply.value = false
    newQuickReplyTitle.value = ''
    newQuickReplyBody.value = ''
    message.success('Шаблон добавлен')
    await loadQuickReplies()
  } catch (err) {
    message.error(err instanceof Error ? err.message : 'Не удалось добавить шаблон')
  }
}

async function hideQuickReplyForMe(template: QuickReplyTemplate): Promise<void> {
  try {
    await hideQuickReply(template.id)
    quickReplies.value = quickReplies.value.filter((item) => item.id !== template.id)
    message.success('Шаблон удалён')
  } catch (err) {
    message.error(err instanceof Error ? err.message : 'Не удалось удалить шаблон')
  }
}

function insertEmoji(emoji: string): void {
  const el = textareaRef.value
  if (el) {
    const start = el.selectionStart ?? text.value.length
    const end = el.selectionEnd ?? start
    text.value = text.value.slice(0, start) + emoji + text.value.slice(end)
    void nextTick(() => {
      el.focus()
      const pos = start + emoji.length
      el.setSelectionRange(pos, pos)
    })
    return
  }
  text.value += emoji
}

watch(quickReplyQuery, scheduleQuickRepliesLoad)

watch(
  () => [props.departmentId, props.groupId],
  () => {
    if (quickRepliesOpen.value) void loadQuickReplies()
  },
)
</script>

<template>
  <div
    class="message-input"
    :class="{
      'message-input--disabled': disabled,
      'message-input--drag-over': dragOver,
    }"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <div v-if="replyTo" class="message-input__reply">
      <div class="message-input__reply-body">
        <strong>Ответ на сообщение</strong>
        <span>{{ replyPreview }}</span>
      </div>
      <button
        type="button"
        class="message-input__reply-cancel"
        aria-label="Отменить ответ"
        @click="emit('cancelReply')"
      >
        <X :size="14" />
      </button>
    </div>

    <div v-if="pendingFiles.length" class="message-input__files">
      <span v-for="f in pendingFiles" :key="f.file_id" class="message-input__file-tag">
        {{ f.name }}
        <button
          type="button"
          class="message-input__file-remove"
          :aria-label="`Убрать ${f.name}`"
          @click="removePending(f.file_id)"
        >
          <X :size="12" />
        </button>
      </span>
    </div>

    <div v-if="quickRepliesOpen" class="message-input__quick-replies">
      <div class="message-input__quick-replies-head">
        <strong>Быстрые ответы</strong>
        <div class="message-input__quick-replies-actions">
          <NButton quaternary size="small" :disabled="disabled" @click="startCreateQuickReply">
            <template #icon><Plus :size="14" /></template>
          </NButton>
          <NButton quaternary size="small" @click="quickRepliesOpen = false">
            <template #icon><X :size="14" /></template>
          </NButton>
        </div>
      </div>

      <div v-if="creatingQuickReply" class="message-input__quick-form">
        <input
          v-model="newQuickReplyTitle"
          class="message-input__quick-input"
          placeholder="Название"
          :disabled="disabled"
        />
        <textarea
          v-model="newQuickReplyBody"
          class="message-input__quick-textarea"
          rows="3"
          placeholder="Текст быстрого ответа"
          :disabled="disabled"
        />
        <div class="message-input__quick-form-actions">
          <NButton size="small" @click="creatingQuickReply = false">Отмена</NButton>
          <NButton size="small" type="primary" @click="saveQuickReply">Сохранить</NButton>
        </div>
      </div>

      <div v-else-if="quickReplies.length" class="message-input__quick-list">
        <div
          v-for="reply in quickReplies"
          :key="reply.id"
          class="message-input__quick-item"
          role="button"
          tabindex="0"
          @click="applyQuickReply(reply)"
          @keydown.enter.prevent="applyQuickReply(reply)"
        >
          <span class="message-input__quick-main">
            <strong>{{ reply.title }}</strong>
            <small>{{ reply.body }}</small>
          </span>
          <button
            type="button"
            class="message-input__quick-delete"
            aria-label="Скрыть шаблон для себя"
            @click.stop="hideQuickReplyForMe(reply)"
          >
            <Trash2 :size="14" />
          </button>
        </div>
      </div>
      <div v-else class="message-input__quick-empty">
        {{ quickRepliesLoading ? 'Ищем...' : 'Подходящих шаблонов нет' }}
      </div>
    </div>

    <div class="message-input__row">
      <div class="message-input__attach">
        <EmojiPicker :disabled="disabled" @pick="insertEmoji" />
        <NButton quaternary :disabled="disabled" aria-label="Быстрые ответы" @click="openQuickReplies">
          <template #icon><MessageSquareText :size="18" /></template>
        </NButton>
        <NUpload :show-file-list="false" @before-upload="onBeforeUpload">
          <NButton quaternary :disabled="disabled" aria-label="Прикрепить файл">
            <template #icon><Paperclip :size="18" /></template>
          </NButton>
        </NUpload>
        <NButton
          quaternary
          :disabled="disabled"
          aria-label="Хранилище"
          title="Хранилище / файлы диалога"
          @click="openVaultPicker"
        >
          <template #icon><FolderOpen :size="18" /></template>
        </NButton>
      </div>

      <textarea
        ref="textareaRef"
        v-model="text"
        class="message-input__textarea"
        rows="1"
        :disabled="disabled"
        :placeholder="placeholder ?? 'Сообщение…'"
        title="Enter — отправить, Shift+Enter — новая строка"
        aria-label="Текст сообщения"
        @keydown="onKeydown"
        @paste="onPaste"
      />

      <NButton
        class="message-input__send"
        type="primary"
        :disabled="disabled || (!text.trim() && !pendingFiles.length)"
        :loading="sending"
        aria-label="Отправить"
        @click="submit"
      >
        <template #icon><Send :size="16" /></template>
      </NButton>
    </div>
    <VaultFilePickerModal
      v-model:show="vaultPickerOpen"
      :chat-id="chatId ?? null"
      @select="onVaultFileSelect"
    />
  </div>
</template>

<style scoped>
.message-input {
  flex-shrink: 0;
  padding: 12px 16px;
  border-top: 1px solid var(--app-border);
  background: var(--app-surface);
  transition: background 0.15s, outline 0.15s;
}

.message-input--drag-over {
  outline: 2px dashed var(--app-accent);
  outline-offset: -4px;
  background: var(--app-accent-soft);
}

.message-input--disabled {
  opacity: 0.65;
  pointer-events: none;
}

.message-input__reply {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  padding: 7px 9px;
  border-left: 3px solid var(--app-accent);
  border-radius: 8px;
  background: var(--app-surface-elevated);
}

.message-input__reply-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 0.8rem;
}

.message-input__reply-body span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-text-muted);
}

.message-input__reply-cancel {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  flex-shrink: 0;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.message-input__reply-cancel:hover {
  background: rgba(127, 127, 127, 0.16);
}

.message-input__files {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.message-input__file-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.8rem;
  padding: 2px 8px;
  border-radius: var(--app-control-radius, 8px);
  background: var(--app-surface-elevated);
}

.message-input__file-remove {
  display: inline-flex;
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
  opacity: 0.7;
  color: inherit;
}

.message-input__file-remove:hover {
  opacity: 1;
}

.message-input__row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: end;
  gap: 8px;
  width: 100%;
}

.message-input__quick-replies {
  margin-bottom: 8px;
  padding: 10px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface-elevated);
}

.message-input__quick-replies-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.message-input__quick-replies-actions,
.message-input__quick-form-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
}

.message-input__quick-list,
.message-input__quick-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.message-input__quick-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: var(--app-surface);
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.message-input__quick-item:hover,
.message-input__quick-item:focus-visible {
  border-color: var(--app-accent);
  outline: none;
}

.message-input__quick-main {
  min-width: 0;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
}

.message-input__quick-main strong,
.message-input__quick-main small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.message-input__quick-main small,
.message-input__quick-empty {
  color: var(--app-text-muted);
  font-size: 0.8125rem;
}

.message-input__quick-delete {
  display: inline-flex;
  flex-shrink: 0;
  padding: 4px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--app-text-muted);
  cursor: pointer;
}

.message-input__quick-delete:hover {
  color: var(--app-danger);
  background: var(--app-danger-soft);
}

.message-input__quick-input,
.message-input__quick-textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface);
  color: var(--app-text);
  font: inherit;
}

.message-input__quick-textarea {
  resize: vertical;
}

.message-input__attach {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 2px;
}

.message-input__send {
  flex-shrink: 0;
}

.message-input__textarea {
  display: block;
  width: 100%;
  min-width: 0;
  min-height: 42px;
  max-height: 160px;
  margin: 0;
  padding: 9px 12px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-control-radius, 8px);
  background: var(--app-surface-elevated);
  color: var(--app-text);
  font: inherit;
  line-height: 1.4;
  resize: vertical;
  box-sizing: border-box;
}

.message-input__textarea::placeholder {
  color: var(--app-text-muted);
}

.message-input__textarea:focus {
  outline: none;
  border-color: var(--app-accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--app-accent) 22%, transparent);
}

.message-input__textarea:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
</style>
