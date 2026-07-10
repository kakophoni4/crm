<script setup lang="ts">
import { NButton, NEmpty, NModal, NSpin, NTag, NTooltip, useMessage } from 'naive-ui'
import { Download, Eye, FolderOpen, FolderPlus, Send } from 'lucide-vue-next'
import { computed, onUnmounted, ref, watch } from 'vue'

import {
  downloadGroupFile,
  listGroupFiles,
  uploadVaultFile,
  type GroupChatFile,
} from '@/features/storage/api'
import { AppError } from '@/shared/api/http'
import {
  attachmentPreviewSupported,
  resolveAttachmentPreviewKind,
} from '@/shared/lib/attachment-preview-kind'
import { formatFileSize } from '@/shared/config/uploads'
import AttachmentPreviewModal from '@/widgets/chat/AttachmentPreviewModal.vue'

const props = defineProps<{
  show: boolean
  chatId: number | null
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  select: [file: { file_id: number; name: string; mime?: string }]
}>()

const message = useMessage()
const loading = ref(false)
const files = ref<GroupChatFile[]>([])
const busyId = ref<number | null>(null)

const previewOpen = ref(false)
const previewLoading = ref(false)
const previewName = ref('')
const previewMime = ref('')
const previewBlob = ref<Blob | null>(null)
const previewBlobUrl = ref<string | null>(null)

const previewKind = computed(() =>
  resolveAttachmentPreviewKind({
    name: previewName.value,
    mime: previewMime.value,
  }),
)

async function load(): Promise<void> {
  if (props.chatId == null) {
    files.value = []
    return
  }
  loading.value = true
  try {
    const data = await listGroupFiles({ chat_id: props.chatId, limit: 100 })
    files.value = data.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить файлы диалога')
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.show, props.chatId] as const,
  ([open]) => {
    if (open) void load()
  },
)

function onShowUpdate(value: boolean): void {
  emit('update:show', value)
}

function senderLabel(file: GroupChatFile): string {
  return file.sender_display_name?.trim() || (file.direction === 'inbound' ? 'Клиент' : 'Оператор')
}

function canPreview(file: GroupChatFile): boolean {
  return attachmentPreviewSupported(
    resolveAttachmentPreviewKind({
      name: file.original_name,
      mime: file.mime_type,
    }),
  )
}

function sendFile(file: GroupChatFile): void {
  if (file.file_id == null) {
    message.warning('Файл ещё не готов к повторной отправке')
    return
  }
  emit('select', {
    file_id: file.file_id,
    name: file.original_name,
    mime: file.mime_type,
  })
  emit('update:show', false)
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

async function onDownload(file: GroupChatFile): Promise<void> {
  busyId.value = file.id
  try {
    const blob = await downloadGroupFile(file.id)
    saveBlob(blob, file.original_name)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать файл')
  } finally {
    busyId.value = null
  }
}

function resetPreview(): void {
  if (previewBlobUrl.value) URL.revokeObjectURL(previewBlobUrl.value)
  previewBlobUrl.value = null
  previewBlob.value = null
}

async function onPreview(file: GroupChatFile): Promise<void> {
  if (!canPreview(file)) {
    message.warning('Предпросмотр для этого типа файла недоступен')
    return
  }
  resetPreview()
  previewName.value = file.original_name
  previewMime.value = file.mime_type || ''
  previewOpen.value = true
  previewLoading.value = true
  try {
    const blob = await downloadGroupFile(file.id)
    previewBlob.value = blob
    previewBlobUrl.value = URL.createObjectURL(blob)
  } catch (err) {
    previewOpen.value = false
    message.error(err instanceof AppError ? err.message : 'Не удалось открыть файл')
  } finally {
    previewLoading.value = false
  }
}

function closePreview(): void {
  previewOpen.value = false
  resetPreview()
}

async function onAddToVault(file: GroupChatFile): Promise<void> {
  busyId.value = file.id
  try {
    const blob = await downloadGroupFile(file.id)
    const uploaded = new File([blob], file.original_name, {
      type: file.mime_type || blob.type || 'application/octet-stream',
    })
    await uploadVaultFile(uploaded)
    message.success(`«${file.original_name}» добавлен в Мои файлы`)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось добавить в Мои файлы')
  } finally {
    busyId.value = null
  }
}

onUnmounted(() => {
  resetPreview()
})
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    title="Хранилище диалога"
    style="width: min(640px, 96vw)"
    @update:show="onShowUpdate"
  >
    <NSpin :show="loading">
      <NEmpty v-if="!files.length && !loading" description="В этом диалоге ещё нет файлов" />
      <ul v-else class="file-list">
        <li v-for="file in files" :key="file.id" class="file-item">
          <div class="file-info">
            <FolderOpen :size="16" class="file-icon" />
            <div>
              <div class="file-name">{{ file.original_name }}</div>
              <div class="file-meta">
                {{ formatFileSize(file.size_bytes) }} ·
                {{ new Date(file.created_at).toLocaleString('ru-RU') }}
              </div>
            </div>
          </div>
          <div class="file-actions">
            <NTag size="tiny" :bordered="false" :title="file.direction === 'inbound' ? 'Клиент' : 'Оператор'">
              {{ senderLabel(file) }}
            </NTag>
            <NTooltip>
              <template #trigger>
                <NButton
                  size="tiny"
                  quaternary
                  :disabled="!canPreview(file)"
                  :loading="busyId === file.id && previewLoading"
                  @click="onPreview(file)"
                >
                  <template #icon><Eye :size="14" /></template>
                </NButton>
              </template>
              Предпросмотр
            </NTooltip>
            <NTooltip>
              <template #trigger>
                <NButton
                  size="tiny"
                  quaternary
                  :loading="busyId === file.id"
                  @click="onDownload(file)"
                >
                  <template #icon><Download :size="14" /></template>
                </NButton>
              </template>
              Скачать
            </NTooltip>
            <NTooltip>
              <template #trigger>
                <NButton
                  size="tiny"
                  quaternary
                  :loading="busyId === file.id"
                  @click="onAddToVault(file)"
                >
                  <template #icon><FolderPlus :size="14" /></template>
                </NButton>
              </template>
              В Мои файлы
            </NTooltip>
            <NButton
              size="small"
              type="primary"
              :disabled="file.file_id == null"
              @click="sendFile(file)"
            >
              <template #icon><Send :size="14" /></template>
              Отправить
            </NButton>
          </div>
        </li>
      </ul>
    </NSpin>

    <AttachmentPreviewModal
      :open="previewOpen"
      :loading="previewLoading"
      :label="previewName"
      :blob-url="previewBlobUrl"
      :blob="previewBlob"
      :preview-kind="previewKind"
      @close="closePreview"
    />
  </NModal>
</template>

<style scoped>
.file-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 420px;
  overflow-y: auto;
}

.file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--n-border-color);
}

.file-info {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.file-icon {
  flex-shrink: 0;
  margin-top: 2px;
  opacity: 0.7;
}

.file-name {
  font-size: 0.9rem;
  font-weight: 600;
  word-break: break-word;
}

.file-meta {
  margin-top: 2px;
  font-size: 0.75rem;
  color: var(--app-text-muted);
}

.file-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
}
</style>
