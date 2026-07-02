<script setup lang="ts">
import { NButton, NInput, NSpin, useMessage } from 'naive-ui'
import { Download, Lock } from 'lucide-vue-next'
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { downloadPublicShare, getPublicShareInfo, type PublicShareInfo } from '@/features/storage/api'
import { AppError } from '@/shared/api/http'
import { formatFileSize } from '@/shared/config/uploads'
import AppCard from '@/shared/ui/AppCard.vue'

const route = useRoute()
const message = useMessage()

const token = computed(() => String(route.params.token ?? ''))
const loading = ref(true)
const downloading = ref(false)
const info = ref<PublicShareInfo | null>(null)
const password = ref('')

async function loadInfo(): Promise<void> {
  loading.value = true
  try {
    info.value = await getPublicShareInfo(token.value)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ссылка не найдена')
    info.value = null
  } finally {
    loading.value = false
  }
}

async function download(): Promise<void> {
  if (!info.value) return
  downloading.value = true
  try {
    const blob = await downloadPublicShare(token.value, password.value || null)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = info.value.original_name
    a.click()
    URL.revokeObjectURL(url)
    await loadInfo()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать')
  } finally {
    downloading.value = false
  }
}

const canDownload = computed(
  () => info.value && !info.value.is_expired && !info.value.is_exhausted,
)

onMounted(() => {
  void loadInfo()
})
</script>

<template>
  <div class="share-page">
    <AppCard title="Скачать файл">
      <NSpin :show="loading">
        <template v-if="info">
          <p class="file-name">{{ info.original_name }}</p>
          <p class="meta">{{ formatFileSize(info.size_bytes) }}</p>
          <p v-if="info.expires_at" class="meta">
            Действует до: {{ new Date(info.expires_at).toLocaleString('ru-RU') }}
          </p>
          <p v-if="info.max_downloads != null" class="meta">
            Скачиваний: {{ info.download_count }} / {{ info.max_downloads }}
          </p>
          <p v-if="info.is_expired" class="error">Ссылка истекла</p>
          <p v-else-if="info.is_exhausted" class="error">Лимит скачиваний исчерпан</p>
          <div v-if="canDownload" class="actions">
            <NInput
              v-if="info.has_password"
              v-model:value="password"
              type="password"
              placeholder="Пароль"
              show-password-on="click"
            >
              <template #prefix><Lock :size="14" /></template>
            </NInput>
            <NButton type="primary" :loading="downloading" block @click="download">
              <template #icon><Download :size="16" /></template>
              Скачать
            </NButton>
          </div>
        </template>
        <p v-else-if="!loading">Файл недоступен</p>
      </NSpin>
    </AppCard>
  </div>
</template>

<style scoped>
.share-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: var(--n-body-color);
}

.share-page :deep(.app-card) {
  width: 100%;
  max-width: 420px;
}

.file-name {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 8px;
  word-break: break-word;
}

.meta {
  color: var(--n-text-color-3);
  font-size: 13px;
  margin: 4px 0;
}

.error {
  color: var(--n-error-color);
  margin-top: 12px;
}

.actions {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
