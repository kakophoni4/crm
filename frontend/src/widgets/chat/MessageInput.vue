<script setup lang="ts">
import { NButton, NUpload, useMessage } from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { Paperclip, Send, X } from 'lucide-vue-next'
import { ref } from 'vue'

import { uploadFile } from '@/features/chats/api'
import { formatFileSize, MAX_UPLOAD_BYTES } from '@/shared/config/uploads'
import { isMessageSendShortcut } from '@/widgets/chat/message-input-hotkeys'

const props = defineProps<{
  disabled?: boolean
  placeholder?: string
}>()

const emit = defineEmits<{
  send: [text: string, attachments: { file_id: number; name?: string; mime?: string }[]]
}>()

const message = useMessage()
const text = ref('')
const pendingFiles = ref<{ file_id: number; name: string; mime?: string }[]>([])
const sending = ref(false)
const dragOver = ref(false)

function validateFileSize(file: File): boolean {
  if (file.size <= MAX_UPLOAD_BYTES) return true
  message.error(
    `Файл «${file.name}» слишком большой (макс. ${formatFileSize(MAX_UPLOAD_BYTES)})`,
  )
  return false
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
    )
    text.value = ''
    pendingFiles.value = []
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

    <div class="message-input__row">
      <div class="message-input__attach">
        <NUpload :show-file-list="false" @before-upload="onBeforeUpload">
          <NButton quaternary :disabled="disabled" aria-label="Прикрепить файл">
            <template #icon><Paperclip :size="18" /></template>
          </NButton>
        </NUpload>
      </div>

      <textarea
        v-model="text"
        class="message-input__textarea"
        rows="2"
        :disabled="disabled"
        :placeholder="placeholder ?? 'Сообщение… (Enter — отправить, Shift+Enter — новая строка)'"
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
  outline: 2px dashed var(--app-accent, #2080f0);
  outline-offset: -4px;
  background: var(--app-accent-soft, #e8f3ff);
}

.message-input--disabled {
  opacity: 0.65;
  pointer-events: none;
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
  background: var(--app-surface-elevated, #eee);
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

.message-input__attach {
  flex-shrink: 0;
}

.message-input__send {
  flex-shrink: 0;
}

.message-input__textarea {
  display: block;
  width: 100%;
  min-width: 0;
  min-height: 56px;
  max-height: 160px;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-control-radius, 8px);
  background: var(--app-surface-elevated, #f4f4f5);
  color: var(--app-text);
  font: inherit;
  line-height: 1.5;
  resize: vertical;
  box-sizing: border-box;
}

.message-input__textarea::placeholder {
  color: var(--app-text-muted);
}

.message-input__textarea:focus {
  outline: none;
  border-color: var(--app-accent, #2080f0);
  box-shadow: 0 0 0 2px var(--app-accent-soft, rgba(32, 128, 240, 0.2));
}

.message-input__textarea:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}
</style>
