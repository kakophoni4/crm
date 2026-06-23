<script setup lang="ts">
import { useIntersectionObserver } from '@vueuse/core'
import { Download, RotateCcw, X, ZoomIn, ZoomOut } from 'lucide-vue-next'
import { NButton, NSpin } from 'naive-ui'
import { computed, onUnmounted, ref, watch } from 'vue'

import {
  fetchAttachmentBlobUrl,
  peekAttachmentBlobUrl,
} from '@/shared/lib/attachment-blob-cache'

const props = defineProps<{
  att: unknown
}>()

const rootRef = ref<HTMLElement | null>(null)
const blobUrl = ref<string | null>(null)
const loading = ref(false)
const failed = ref(false)
const visible = ref(false)
const previewOpen = ref(false)
const previewZoom = ref(1)
let loadToken = 0

const row = computed(() => props.att as Record<string, unknown>)

const status = computed(() => String(row.value.status ?? ''))
const downloadPath = computed(() => {
  const path = row.value.download_path
  return typeof path === 'string' && path.length > 0 ? path : null
})
const label = computed(() => {
  const filename = row.value.filename ?? row.value.name
  if (typeof filename === 'string' && filename) return filename
  const fileId = row.value.file_id
  if (typeof fileId === 'number') return `Файл #${fileId}`
  return 'Файл'
})
const failureText = computed(() => {
  const error = row.value.error
  if (typeof error === 'string' && error.trim()) return error.trim()
  return 'Не удалось загрузить файл'
})
const isImage = computed(() => {
  if (status.value !== 'ready' || !downloadPath.value) return false
  if (row.value.type === 'photo') return true
  const mime = row.value.mime
  return typeof mime === 'string' && mime.startsWith('image/')
})
const previewImageStyle = computed(() => ({
  transform: `scale(${previewZoom.value})`,
}))

useIntersectionObserver(
  rootRef,
  ([entry]) => {
    if (entry?.isIntersecting) {
      visible.value = true
    }
  },
  { rootMargin: '120px' },
)

async function load(): Promise<void> {
  const token = ++loadToken
  failed.value = false
  blobUrl.value = null

  if (status.value !== 'ready' || !downloadPath.value || !visible.value) return

  const cached = peekAttachmentBlobUrl(downloadPath.value)
  if (cached) {
    blobUrl.value = cached
    return
  }

  loading.value = true
  try {
    const url = await fetchAttachmentBlobUrl(downloadPath.value)
    if (token !== loadToken) return
    blobUrl.value = url
  } catch {
    if (token !== loadToken) return
    failed.value = true
  } finally {
    if (token === loadToken) {
      loading.value = false
    }
  }
}

function openPreview(): void {
  if (!isImage.value || !blobUrl.value) return
  previewZoom.value = 1
  previewOpen.value = true
}

function closePreview(): void {
  previewOpen.value = false
}

function zoomIn(): void {
  previewZoom.value = Math.min(4, Number((previewZoom.value + 0.25).toFixed(2)))
}

function zoomOut(): void {
  previewZoom.value = Math.max(0.5, Number((previewZoom.value - 0.25).toFixed(2)))
}

function resetZoom(): void {
  previewZoom.value = 1
}

watch(
  () => [status.value, downloadPath.value, visible.value] as const,
  () => void load(),
)

onUnmounted(() => {
  loadToken += 1
})
</script>

<template>
  <span ref="rootRef" class="message-attachment-wrap">
    <span v-if="status === 'pending' || status === 'queued'" class="message-attachment message-attachment--pending">
      Загрузка файла…
    </span>
    <span v-else-if="status === 'failed'" class="message-attachment message-attachment--failed">
      {{ failureText }}
    </span>
    <NSpin v-else-if="loading" size="small" />
    <span v-else-if="failed" class="message-attachment message-attachment--failed">
      {{ label }}
    </span>
    <img
      v-else-if="isImage && blobUrl"
      class="message-attachment__image"
      :src="blobUrl"
      :alt="label"
      role="button"
      tabindex="0"
      title="Открыть изображение"
      @click="openPreview"
      @keydown.enter.prevent="openPreview"
      @keydown.space.prevent="openPreview"
    />
    <a
      v-else-if="blobUrl"
      class="message-attachment__link"
      :href="blobUrl"
      :download="label"
      target="_blank"
      rel="noopener noreferrer"
    >
      {{ label }}
    </a>
    <span v-else class="message-attachment">{{ label }}</span>
  </span>

  <Teleport to="body">
    <div
      v-if="previewOpen && blobUrl"
      class="attachment-preview"
      role="dialog"
      aria-modal="true"
      :aria-label="label"
      tabindex="-1"
      @click.self="closePreview"
      @keydown.esc="closePreview"
    >
      <div class="attachment-preview__toolbar" @click.stop>
        <NButton quaternary circle size="large" title="Уменьшить" @click="zoomOut">
          <template #icon>
            <ZoomOut :size="20" />
          </template>
        </NButton>
        <NButton quaternary circle size="large" title="Сбросить масштаб" @click="resetZoom">
          <template #icon>
            <RotateCcw :size="20" />
          </template>
        </NButton>
        <NButton quaternary circle size="large" title="Увеличить" @click="zoomIn">
          <template #icon>
            <ZoomIn :size="20" />
          </template>
        </NButton>
        <NButton
          quaternary
          circle
          size="large"
          tag="a"
          :href="blobUrl"
          :download="label"
          title="Скачать"
        >
          <template #icon>
            <Download :size="20" />
          </template>
        </NButton>
        <NButton quaternary circle size="large" title="Закрыть" @click="closePreview">
          <template #icon>
            <X :size="22" />
          </template>
        </NButton>
      </div>
      <div class="attachment-preview__stage" @click.stop>
        <img
          class="attachment-preview__image"
          :src="blobUrl"
          :alt="label"
          :style="previewImageStyle"
        />
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.message-attachment-wrap {
  display: block;
}

.message-attachment {
  display: block;
}

.message-attachment--pending {
  opacity: 0.7;
  font-style: italic;
}

.message-attachment--failed {
  color: #d03050;
}

.message-attachment__image {
  max-width: 100%;
  max-height: 280px;
  border-radius: 8px;
  display: block;
  cursor: zoom-in;
}

.message-attachment__link {
  color: var(--app-accent, #2080f0);
  word-break: break-all;
}

.attachment-preview {
  position: fixed;
  inset: 0;
  z-index: 4000;
  display: grid;
  grid-template-rows: auto 1fr;
  background: rgb(8 12 20 / 92%);
  backdrop-filter: blur(6px);
}

.attachment-preview__toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px;
  background: linear-gradient(to bottom, rgb(8 12 20 / 72%), transparent);
}

.attachment-preview__toolbar :deep(.n-button) {
  color: #fff;
}

.attachment-preview__stage {
  min-height: 0;
  overflow: auto;
  display: grid;
  place-items: center;
  padding: 16px;
}

.attachment-preview__image {
  max-width: min(96vw, 1600px);
  max-height: 88vh;
  display: block;
  border-radius: 8px;
  object-fit: contain;
  transform-origin: center center;
  transition: transform 120ms ease;
  box-shadow: 0 24px 80px rgb(0 0 0 / 45%);
}

@media (max-width: 640px) {
  .attachment-preview__toolbar {
    justify-content: center;
    padding: 8px;
  }

  .attachment-preview__stage {
    padding: 8px;
  }
}
</style>
