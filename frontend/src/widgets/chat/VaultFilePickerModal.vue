<script setup lang="ts">
import { NButton, NEmpty, NModal, NSpin, useMessage } from 'naive-ui'
import { FolderOpen } from 'lucide-vue-next'
import { ref, watch } from 'vue'

import { listVaultFiles, type VaultFile } from '@/features/storage/api'
import { AppError } from '@/shared/api/http'
import { formatFileSize } from '@/shared/config/uploads'

const props = defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  select: [file: { file_id: number; name: string; mime?: string }]
}>()

const message = useMessage()
const loading = ref(false)
const files = ref<VaultFile[]>([])

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listVaultFiles({ limit: 100 })
    files.value = data.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить хранилище')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.show,
  (open) => {
    if (open) void load()
  },
)

function onShowUpdate(value: boolean): void {
  emit('update:show', value)
}

function pick(file: VaultFile): void {
  emit('select', {
    file_id: file.file_id,
    name: file.original_name,
    mime: file.mime_type,
  })
  emit('update:show', false)
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    title="Файлы из хранилища"
    style="width: 520px"
    @update:show="onShowUpdate"
  >
    <NSpin :show="loading">
      <NEmpty v-if="!files.length && !loading" description="Хранилище пусто" />
      <ul v-else class="file-list">
        <li v-for="file in files" :key="file.id" class="file-item">
          <div class="file-info">
            <FolderOpen :size="16" class="file-icon" />
            <div>
              <div class="file-name">{{ file.original_name }}</div>
              <div class="file-meta">{{ formatFileSize(file.size_bytes) }}</div>
            </div>
          </div>
          <NButton size="small" type="primary" @click="pick(file)">Выбрать</NButton>
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
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.file-name {
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta {
  font-size: 12px;
  color: var(--n-text-color-3);
}

.file-icon {
  flex-shrink: 0;
  opacity: 0.7;
}
</style>
