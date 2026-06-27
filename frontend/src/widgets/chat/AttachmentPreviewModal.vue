<script setup lang="ts">
import { Download, RotateCcw, X, ZoomIn, ZoomOut } from 'lucide-vue-next'
import { NButton, NSpin } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import type { AttachmentPreviewKind } from '@/shared/lib/attachment-preview-kind'
import { renderAttachmentPreviewHtml } from '@/shared/lib/attachment-preview-render'

const props = defineProps<{
  open: boolean
  loading?: boolean
  label: string
  blobUrl: string | null
  blob: Blob | null
  previewKind: AttachmentPreviewKind
}>()

const emit = defineEmits<{
  close: []
}>()

const previewZoom = ref(1)
const htmlPreview = ref<string | null>(null)
const htmlLoading = ref(false)
const htmlError = ref(false)

const canZoom = computed(
  () =>
    props.previewKind === 'image' ||
    props.previewKind === 'pdf' ||
    props.previewKind === 'text' ||
    props.previewKind === 'docx' ||
    props.previewKind === 'spreadsheet',
)

const stageStyle = computed(() => ({
  transform: props.previewKind === 'image' || props.previewKind === 'pdf' ? `scale(${previewZoom.value})` : undefined,
}))

const pdfSrc = computed(() => {
  if (!props.blobUrl || props.previewKind !== 'pdf') return null
  return `${props.blobUrl}#view=FitH&toolbar=1`
})

const htmlStageStyle = computed(() => ({
  transform:
    props.previewKind === 'text' ||
    props.previewKind === 'docx' ||
    props.previewKind === 'spreadsheet'
      ? `scale(${previewZoom.value})`
      : undefined,
}))

watch(
  () => [props.open, props.blob, props.previewKind] as const,
  async ([open, blob, kind]) => {
    htmlPreview.value = null
    htmlError.value = false
    if (!open || !blob) return
    if (kind !== 'text' && kind !== 'docx' && kind !== 'spreadsheet') return
    htmlLoading.value = true
    try {
      htmlPreview.value = await renderAttachmentPreviewHtml(kind, blob)
    } catch {
      htmlError.value = true
    } finally {
      htmlLoading.value = false
    }
  },
  { immediate: true },
)

watch(
  () => props.open,
  (open) => {
    if (open) previewZoom.value = 1
  },
)

function zoomIn(): void {
  previewZoom.value = Math.min(4, Number((previewZoom.value + 0.25).toFixed(2)))
}

function zoomOut(): void {
  previewZoom.value = Math.max(0.5, Number((previewZoom.value - 0.25).toFixed(2)))
}

function resetZoom(): void {
  previewZoom.value = 1
}

function download(): void {
  if (!props.blobUrl) return
  const anchor = document.createElement('a')
  anchor.href = props.blobUrl
  anchor.download = props.label
  anchor.rel = 'noopener'
  anchor.click()
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="attachment-preview"
      role="dialog"
      aria-modal="true"
      :aria-label="label"
      tabindex="-1"
      @click="emit('close')"
      @keydown.esc="emit('close')"
    >
      <div class="attachment-preview__toolbar" @click.stop>
        <span class="attachment-preview__title">{{ label }}</span>
        <div class="attachment-preview__actions">
          <NButton v-if="canZoom && blobUrl" quaternary circle size="large" title="Уменьшить" @click="zoomOut">
            <template #icon>
              <ZoomOut :size="20" />
            </template>
          </NButton>
          <NButton v-if="canZoom && blobUrl" quaternary circle size="large" title="Сбросить масштаб" @click="resetZoom">
            <template #icon>
              <RotateCcw :size="20" />
            </template>
          </NButton>
          <NButton v-if="canZoom && blobUrl" quaternary circle size="large" title="Увеличить" @click="zoomIn">
            <template #icon>
              <ZoomIn :size="20" />
            </template>
          </NButton>
          <NButton
            quaternary
            circle
            size="large"
            title="Скачать"
            :disabled="!blobUrl"
            @click="download"
          >
            <template #icon>
              <Download :size="20" />
            </template>
          </NButton>
          <NButton quaternary circle size="large" title="Закрыть" @click="emit('close')">
            <template #icon>
              <X :size="22" />
            </template>
          </NButton>
        </div>
      </div>

      <div class="attachment-preview__stage" @click.stop>
        <NSpin v-if="loading && !blobUrl" size="large" />
        <div v-else-if="!blobUrl" class="attachment-preview__fallback">
          <p>Не удалось загрузить файл для предпросмотра.</p>
        </div>
        <img
          v-else-if="previewKind === 'image'"
          class="attachment-preview__image"
          :src="blobUrl"
          :alt="label"
          :style="stageStyle"
        />
        <div
          v-else-if="previewKind === 'pdf'"
          class="attachment-preview__pdf-wrap"
          :style="stageStyle"
        >
          <iframe class="attachment-preview__pdf" :src="pdfSrc ?? blobUrl" :title="label" />
        </div>
        <NSpin v-else-if="htmlLoading" size="large" />
        <div v-else-if="htmlError" class="attachment-preview__fallback">
          <p>Не удалось построить предпросмотр.</p>
          <NButton type="primary" @click="download">Скачать файл</NButton>
        </div>
        <div
          v-else-if="htmlPreview"
          class="attachment-preview__html-wrap"
          :style="htmlStageStyle"
          v-html="htmlPreview"
        />
        <div v-else class="attachment-preview__fallback">
          <p>Предпросмотр для этого типа файла недоступен.</p>
          <NButton type="primary" @click="download">Скачать файл</NButton>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
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
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: linear-gradient(to bottom, rgb(8 12 20 / 72%), transparent);
}

.attachment-preview__title {
  color: #fff;
  font-size: 0.9rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.attachment-preview__actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
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

.attachment-preview__pdf-wrap {
  width: min(96vw, 1200px);
  height: 88vh;
  transform-origin: center center;
  transition: transform 120ms ease;
}

.attachment-preview__pdf {
  width: 100%;
  height: 100%;
  border: 0;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 24px 80px rgb(0 0 0 / 45%);
}

.attachment-preview__html-wrap {
  width: min(96vw, 1200px);
  max-height: 88vh;
  overflow: auto;
  transform-origin: top center;
  transition: transform 120ms ease;
  background: #fff;
  color: #111;
  border-radius: 8px;
  padding: 16px 20px;
  box-shadow: 0 24px 80px rgb(0 0 0 / 45%);
}

.attachment-preview__html-wrap :deep(.attachment-preview-text) {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.88rem;
  line-height: 1.5;
}

.attachment-preview__html-wrap :deep(table) {
  border-collapse: collapse;
  width: 100%;
  font-size: 0.85rem;
}

.attachment-preview__html-wrap :deep(th),
.attachment-preview__html-wrap :deep(td) {
  border: 1px solid #ddd;
  padding: 6px 8px;
}

.attachment-preview__fallback {
  color: #fff;
  text-align: center;
  display: grid;
  gap: 12px;
}

@media (max-width: 640px) {
  .attachment-preview__toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .attachment-preview__actions {
    justify-content: center;
  }

  .attachment-preview__stage {
    padding: 8px;
  }
}
</style>
