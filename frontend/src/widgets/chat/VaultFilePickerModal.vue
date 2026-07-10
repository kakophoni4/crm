<script setup lang="ts">
import { NButton, NEmpty, NModal, NSpin, NTabPane, NTabs, NTag, NTooltip, useMessage } from 'naive-ui'
import { Download, Eye, FolderOpen, FolderPlus, Send } from 'lucide-vue-next'
import { computed, onUnmounted, ref, watch } from 'vue'

import {
  downloadGroupFile,
  listGroupFiles,
  listVaultFiles,
  uploadVaultFile,
  type GroupChatFile,
  type VaultFile,
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
  chatId?: number | null
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  select: [file: { file_id: number; name: string; mime?: string }]
}>()

const message = useMessage()
const activeTab = ref<'vault' | 'dialog'>('vault')
const loading = ref(false)
const vaultFiles = ref<VaultFile[]>([])
const dialogFiles = ref<GroupChatFile[]>([])
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

const hasChat = computed(() => props.chatId != null)

async function loadVault(): Promise<void> {
  loading.value = true
  try {
    const data = await listVaultFiles({ limit: 100 })
    vaultFiles.value = data.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить хранилище')
  } finally {
    loading.value = false
  }
}

async function loadDialog(): Promise<void> {
  if (props.chatId == null) {
    dialogFiles.value = []
    return
  }
  loading.value = true
  try {
    const data = await listGroupFiles({ chat_id: props.chatId, limit: 100 })
    dialogFiles.value = data.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить файлы диалога')
  } finally {
    loading.value = false
  }
}

async function loadActive(): Promise<void> {
  if (activeTab.value === 'dialog') await loadDialog()
  else await loadVault()
}

watch(
  () => props.show,
  (open) => {
    if (!open) return
    activeTab.value = 'vault'
    void loadActive()
  },
)

watch(activeTab, () => {
  if (props.show) void loadActive()
})

function onShowUpdate(value: boolean): void {
  emit('update:show', value)
}

function pickVault(file: VaultFile): void {
  emit('select', {
    file_id: file.file_id,
    name: file.original_name,
    mime: file.mime_type,
  })
  emit('update:show', false)
}

function pickDialog(file: GroupChatFile): void {
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

function senderLabel(file: GroupChatFile): string {
  return file.sender_display_name?.trim() || (file.direction === 'inbound' ? 'Клиент' : 'Оператор')
}

function canPreview(name: string, mime: string): boolean {
  return attachmentPreviewSupported(resolveAttachmentPreviewKind({ name, mime }))
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function resetPreview(): void {
  if (previewBlobUrl.value) URL.revokeObjectURL(previewBlobUrl.value)
  previewBlobUrl.value = null
  previewBlob.value = null
}

async function openPreview(name: string, mime: string, load: () => Promise<Blob>): Promise<void> {
  if (!canPreview(name, mime)) {
    message.warning('Предпросмотр для этого типа файла недоступен')
    return
  }
  resetPreview()
  previewName.value = name
  previewMime.value = mime || ''
  previewOpen.value = true
  previewLoading.value = true
  try {
    const blob = await load()
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

async function onDownloadDialog(file: GroupChatFile): Promise<void> {
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

async function onPreviewDialog(file: GroupChatFile): Promise<void> {
  busyId.value = file.id
  await openPreview(file.original_name, file.mime_type || '', () => downloadGroupFile(file.id))
  busyId.value = null
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
    title="Файлы"
    style="width: min(640px, 96vw)"
    @update:show="onShowUpdate"
  >
    <NTabs v-model:value="activeTab" type="line" size="small">
      <NTabPane name="vault" tab="Хранилище" />
      <NTabPane name="dialog" tab="Текущий диалог" :disabled="!hasChat" />
    </NTabs>

    <NSpin :show="loading">
      <template v-if="activeTab === 'vault'">
        <NEmpty v-if="!vaultFiles.length && !loading" description="Хранилище пусто" />
        <ul v-else class="file-list">
          <li v-for="file in vaultFiles" :key="file.id" class="file-item">
            <div class="file-info">
              <FolderOpen :size="16" class="file-icon" />
              <div>
                <div class="file-name">{{ file.original_name }}</div>
                <div class="file-meta">{{ formatFileSize(file.size_bytes) }}</div>
              </div>
            </div>
            <NButton size="small" type="primary" @click="pickVault(file)">Выбрать</NButton>
          </li>
        </ul>
      </template>

      <template v-else>
        <NEmpty
          v-if="!hasChat"
          description="Откройте чат, чтобы видеть файлы переписки"
        />
        <NEmpty
          v-else-if="!dialogFiles.length && !loading"
          description="В этом диалоге ещё нет файлов"
        />
        <ul v-else class="file-list">
          <li v-for="file in dialogFiles" :key="file.id" class="file-item">
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
              <NTag size="tiny" :bordered="false">{{ senderLabel(file) }}</NTag>
              <NTooltip>
                <template #trigger>
                  <NButton
                    size="tiny"
                    quaternary
                    :disabled="!canPreview(file.original_name, file.mime_type)"
                    @click="onPreviewDialog(file)"
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
                    @click="onDownloadDialog(file)"
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
                @click="pickDialog(file)"
              >
                <template #icon><Send :size="14" /></template>
                Отправить
              </NButton>
            </div>
          </li>
        </ul>
      </template>
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
  margin: 8px 0 0;
  padding: 0;
  max-height: 400px;
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
  gap: 10px;
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
