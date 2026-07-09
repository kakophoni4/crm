<script setup lang="ts">
import {
  NButton,
  NInput,
  NInputNumber,
  NSpace,
  NUpload,
  useMessage,
} from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { Copy, Link2, Upload } from 'lucide-vue-next'
import { ref } from 'vue'

import { createAnonymousShare } from '@/features/storage/api'
import { AppError } from '@/shared/api/http'
import { formatFileSize, maxUploadBytesFor, uploadLimitLabel } from '@/shared/config/uploads'
import AppCard from '@/shared/ui/AppCard.vue'

const message = useMessage()

const selectedFile = ref<File | null>(null)
const expiresHours = ref<number | null>(168)
const maxDownloads = ref<number | null>(null)
const password = ref('')
const loading = ref(false)
const resultUrl = ref<string | null>(null)

async function onBeforeUpload(data: { file: UploadFileInfo }): Promise<boolean> {
  const file = data.file.file
  if (!file) return false
  if (file.size > maxUploadBytesFor(file)) {
    message.error(`Файл слишком большой (макс. ${uploadLimitLabel(file)})`)
    return false
  }
  selectedFile.value = file
  resultUrl.value = null
  return false
}

async function submit(): Promise<void> {
  if (!selectedFile.value) {
    message.warning('Выберите файл')
    return
  }
  loading.value = true
  try {
    const result = await createAnonymousShare(selectedFile.value, {
      expires_in_hours: expiresHours.value,
      max_downloads: maxDownloads.value,
      password: password.value.trim() || null,
    })
    resultUrl.value = result.url
    await navigator.clipboard.writeText(result.url)
    message.success('Ссылка создана и скопирована')
    selectedFile.value = null
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось создать ссылку')
  } finally {
    loading.value = false
  }
}

function copyUrl(): void {
  if (!resultUrl.value) return
  void navigator.clipboard.writeText(resultUrl.value)
  message.success('Скопировано')
}
</script>

<template>
  <div class="share-upload-page">
    <AppCard title="Передать файл по ссылке">
      <p class="lead">
        Загрузите файл — получите ссылку. Регистрация не нужна, получатель не увидит, кто отправил.
      </p>

      <NSpace vertical :size="14" class="form">
        <NUpload :show-file-list="!!selectedFile" @before-upload="onBeforeUpload">
          <NButton>
            <template #icon><Upload :size="16" /></template>
            Выбрать файл
          </NButton>
        </NUpload>
        <p v-if="selectedFile" class="file-meta">
          {{ selectedFile.name }} · {{ formatFileSize(selectedFile.size) }}
        </p>

        <NInputNumber
          v-model:value="expiresHours"
          :min="1"
          :max="8760"
          placeholder="Срок хранения (часы)"
          style="width: 100%"
        />
        <NInputNumber
          v-model:value="maxDownloads"
          :min="1"
          placeholder="Лимит скачиваний (пусто = без лимита)"
          style="width: 100%"
          clearable
        />
        <NInput
          v-model:value="password"
          type="password"
          placeholder="Пароль для скачивания (необязательно)"
          show-password-on="click"
        />

        <NButton type="primary" block :loading="loading" :disabled="!selectedFile" @click="submit">
          <template #icon><Link2 :size="16" /></template>
          Получить ссылку
        </NButton>

        <div v-if="resultUrl" class="result">
          <p class="result-label">Ссылка для передачи:</p>
          <code class="result-url">{{ resultUrl }}</code>
          <NButton size="small" @click="copyUrl">
            <template #icon><Copy :size="14" /></template>
            Копировать
          </NButton>
        </div>
      </NSpace>
    </AppCard>
  </div>
</template>

<style scoped>
.share-upload-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--app-bg);
}

.share-upload-page :deep(.app-card) {
  width: 100%;
  max-width: 440px;
}

.lead {
  margin: 0 0 16px;
  color: var(--app-text-muted);
  font-size: 0.875rem;
  line-height: 1.5;
}

.file-meta {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--app-text-muted);
}

.result {
  margin-top: 8px;
  padding: 12px;
  border-radius: 8px;
  background: var(--app-surface-elevated);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-label {
  margin: 0;
  font-size: 0.8125rem;
  font-weight: 600;
}

.result-url {
  word-break: break-all;
  font-size: 0.75rem;
}
</style>
