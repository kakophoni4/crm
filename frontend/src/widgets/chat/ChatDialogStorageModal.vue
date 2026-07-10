<script setup lang="ts">
import { NButton, NEmpty, NModal, NSpin, NTag, useMessage } from 'naive-ui'
import { FolderOpen, Send } from 'lucide-vue-next'
import { ref, watch } from 'vue'

import { listGroupFiles, type GroupChatFile } from '@/features/storage/api'
import { AppError } from '@/shared/api/http'
import { formatFileSize } from '@/shared/config/uploads'

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

function directionLabel(direction: string): string {
  return direction === 'inbound' ? 'клиент' : 'оператор'
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    title="Хранилище диалога"
    style="width: 560px"
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
                {{ file.sender_display_name }} ·
                {{ new Date(file.created_at).toLocaleString('ru-RU') }}
              </div>
            </div>
          </div>
          <div class="file-actions">
            <NTag size="tiny" :bordered="false">
              {{ directionLabel(file.direction) }}
            </NTag>
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
  gap: 8px;
  flex-shrink: 0;
}
</style>
