<script setup lang="ts">
import { useIntersectionObserver } from '@vueuse/core'
import { NSpin } from 'naive-ui'
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
}

.message-attachment__link {
  color: var(--app-accent, #2080f0);
  word-break: break-all;
}
</style>
