<script setup lang="ts">
import { useIntersectionObserver } from '@vueuse/core'
import { Download, Eye, FileSpreadsheet, FileText, Image as ImageIcon } from 'lucide-vue-next'
import { NButton, NSpin } from 'naive-ui'
import { computed, onUnmounted, ref, watch } from 'vue'

import {
  fetchAttachmentBlob,
  peekAttachmentBlob,
} from '@/shared/lib/attachment-blob-cache'
import {
  attachmentPreviewSupported,
  resolveAttachmentPreviewKind,
} from '@/shared/lib/attachment-preview-kind'
import AttachmentPreviewModal from '@/widgets/chat/AttachmentPreviewModal.vue'

const props = withDefaults(
  defineProps<{
    att: unknown
    /** Skip viewport gate — load immediately (open chat). */
    eager?: boolean
  }>(),
  { eager: false },
)

const rootRef = ref<HTMLElement | null>(null)
const blobUrl = ref<string | null>(null)
const blob = ref<Blob | null>(null)
const loading = ref(false)
const failed = ref(false)
const visible = ref(props.eager)
const previewOpen = ref(false)
const previewLoading = ref(false)
let loadToken = 0

const row = computed(() => props.att as Record<string, unknown>)

const status = computed(() => String(row.value.status ?? ''))
const downloadPath = computed(() => {
  const path = row.value.download_path
  return typeof path === 'string' && path.length > 0 ? path : null
})
const mime = computed(() => {
  const value = row.value.mime
  return typeof value === 'string' ? value : null
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
const previewKind = computed(() => resolveAttachmentPreviewKind(row.value))
const isImage = computed(() => previewKind.value === 'image')
const isReady = computed(() => status.value === 'ready' && downloadPath.value != null)
const canPreview = computed(() => attachmentPreviewSupported(previewKind.value))
const docIcon = computed(() => {
  if (previewKind.value === 'spreadsheet') return FileSpreadsheet
  if (isImage.value) return ImageIcon
  return FileText
})

useIntersectionObserver(
  rootRef,
  ([entry]) => {
    if (entry?.isIntersecting) {
      visible.value = true
    }
  },
  { rootMargin: '120px' },
)

function applyCached(path: string): boolean {
  const cached = peekAttachmentBlob(path)
  if (!cached) return false
  blobUrl.value = cached.url
  blob.value = cached.blob
  return true
}

async function load(): Promise<void> {
  if (!isReady.value || !downloadPath.value || !visible.value) return
  if (applyCached(downloadPath.value)) return
  if (blobUrl.value || loading.value) return

  const token = ++loadToken
  failed.value = false
  blobUrl.value = null
  blob.value = null

  loading.value = true
  try {
    const entry = await fetchAttachmentBlob(downloadPath.value, mime.value)
    if (token !== loadToken) return
    blobUrl.value = entry.url
    blob.value = entry.blob
  } catch {
    if (token !== loadToken) return
    failed.value = true
  } finally {
    if (token === loadToken) {
      loading.value = false
    }
  }
}

async function ensureBlobLoaded(): Promise<boolean> {
  if (blobUrl.value) return true
  if (downloadPath.value && applyCached(downloadPath.value)) return true
  if (!isReady.value || !downloadPath.value) return false
  await load()
  return blobUrl.value != null
}

async function openPreview(): Promise<void> {
  previewOpen.value = true
  if (blobUrl.value) return
  previewLoading.value = true
  try {
    const ok = await ensureBlobLoaded()
    if (!ok) previewOpen.value = false
  } finally {
    previewLoading.value = false
  }
}

async function downloadFile(): Promise<void> {
  if (!blobUrl.value) {
    previewLoading.value = true
    try {
      const ok = await ensureBlobLoaded()
      if (ok) triggerDownload()
    } finally {
      previewLoading.value = false
    }
    return
  }
  triggerDownload()
}

function triggerDownload(): void {
  if (!blobUrl.value) return
  const anchor = document.createElement('a')
  anchor.href = blobUrl.value
  anchor.download = label.value
  anchor.rel = 'noopener'
  anchor.click()
}

watch(
  () => [status.value, downloadPath.value, visible.value] as const,
  () => void load(),
  { immediate: true },
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
    <span v-else-if="!downloadPath && status === 'ready'" class="message-attachment message-attachment--failed">
      {{ label }} — файл недоступен
    </span>
    <NSpin v-else-if="isImage && !blobUrl && (loading || previewLoading)" size="small" />
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
    <NSpin v-else-if="!isImage && isReady && !blobUrl && (loading || previewLoading)" size="small" />
    <div v-else-if="!isImage && isReady" class="message-attachment__doc">
      <button
        type="button"
        class="message-attachment__doc-main"
        :disabled="previewLoading"
        @click="openPreview"
      >
        <component :is="docIcon" :size="18" class="message-attachment__doc-icon" />
        <span class="message-attachment__doc-name" :title="label">{{ label }}</span>
        <NSpin v-if="(loading || previewLoading) && !blobUrl" size="small" />
      </button>
      <div class="message-attachment__doc-actions">
        <NButton
          size="tiny"
          quaternary
          :loading="previewLoading && !blobUrl"
          title="Открыть"
          @click.stop="openPreview"
        >
          <template #icon>
            <Eye :size="14" />
          </template>
        </NButton>
        <NButton
          size="tiny"
          quaternary
          :loading="(loading || previewLoading) && !blobUrl"
          title="Скачать"
          @click.stop="downloadFile"
        >
          <template #icon>
            <Download :size="14" />
          </template>
        </NButton>
      </div>
    </div>
    <span v-else-if="failed" class="message-attachment message-attachment--failed">
      {{ label }}
      <NButton size="tiny" quaternary @click="load">Повторить</NButton>
    </span>
    <span v-else class="message-attachment">{{ label }}</span>
  </span>

  <AttachmentPreviewModal
    :open="previewOpen"
    :loading="previewLoading || (loading && !blobUrl)"
    :label="label"
    :blob-url="blobUrl"
    :blob="blob"
    :preview-kind="canPreview ? previewKind : 'unsupported'"
    @close="previewOpen = false"
  />
</template>

<style scoped>
.message-attachment-wrap {
  display: block;
  max-width: min(180px, 100%);
}

.message-attachment {
  display: block;
}

.message-attachment--pending {
  opacity: 0.7;
  font-style: italic;
}

.message-attachment--failed {
  color: var(--app-danger);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.message-attachment__image {
  display: block;
  width: 180px;
  height: 180px;
  max-width: 100%;
  object-fit: cover;
  border-radius: 8px;
  cursor: zoom-in;
}

.message-attachment__doc {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--app-border, rgb(255 255 255 / 12%));
  border-radius: 10px;
  background: rgb(255 255 255 / 4%);
}

.message-attachment__doc-main {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
  padding: 0;
}

.message-attachment__doc-main:disabled {
  cursor: wait;
  opacity: 0.7;
}

.message-attachment__doc-icon {
  flex-shrink: 0;
  color: var(--app-accent);
}

.message-attachment__doc-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.88rem;
}

.message-attachment__doc-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}
</style>
