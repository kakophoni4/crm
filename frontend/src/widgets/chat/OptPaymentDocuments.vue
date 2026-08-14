<script setup lang="ts">
import { Download, Eye } from 'lucide-vue-next'
import { NButton, useMessage } from 'naive-ui'
import { computed, ref } from 'vue'

import { downloadOptPaymentDocument } from '@/features/leads/opt-api'
import type { OptPayment, OptPaymentDocument } from '@/features/leads/opt-types'
import {
  resolveAttachmentPreviewKind,
  type AttachmentPreviewKind,
} from '@/shared/lib/attachment-preview-kind'
import { AppError } from '@/shared/api/http'
import AttachmentPreviewModal from '@/widgets/chat/AttachmentPreviewModal.vue'

const props = defineProps<{
  leadId: number
  orderId: number
  payment: Pick<OptPayment, 'id' | 'documents' | 'document_file_id' | 'document_name'>
  compact?: boolean
}>()

const message = useMessage()
const busyKey = ref<string | null>(null)
const previewOpen = ref(false)
const previewLoading = ref(false)
const previewName = ref('')
const previewMime = ref('')
const previewBlob = ref<Blob | null>(null)
const previewBlobUrl = ref<string | null>(null)
const previewKind = computed<AttachmentPreviewKind>(() =>
  previewName.value
    ? resolveAttachmentPreviewKind({ name: previewName.value, mime: previewMime.value })
    : 'unsupported',
)

const documents = computed<OptPaymentDocument[]>(() => {
  const docs = props.payment.documents ?? []
  if (docs.length) return docs
  if (props.payment.document_file_id) {
    return [
      {
        file_id: props.payment.document_file_id,
        name: props.payment.document_name || 'Подтверждение оплаты',
      },
    ]
  }
  return []
})

function resetPreview(): void {
  if (previewBlobUrl.value) URL.revokeObjectURL(previewBlobUrl.value)
  previewBlobUrl.value = null
  previewBlob.value = null
}

async function loadBlob(fileId?: number | null): Promise<Blob> {
  return downloadOptPaymentDocument(props.leadId, props.orderId, props.payment.id, fileId)
}

async function onPreview(doc: OptPaymentDocument): Promise<void> {
  const key = `preview:${doc.file_id}`
  busyKey.value = key
  resetPreview()
  previewName.value = doc.name || 'Подтверждение оплаты'
  previewMime.value = ''
  previewOpen.value = true
  previewLoading.value = true
  try {
    const blob = await loadBlob(doc.file_id)
    previewBlob.value = blob
    previewBlobUrl.value = URL.createObjectURL(blob)
    previewMime.value = blob.type || ''
  } catch (err) {
    previewOpen.value = false
    message.error(err instanceof AppError ? err.message : 'Не удалось открыть документ')
  } finally {
    previewLoading.value = false
    busyKey.value = null
  }
}

async function onDownload(doc: OptPaymentDocument): Promise<void> {
  const key = `dl:${doc.file_id}`
  busyKey.value = key
  try {
    const blob = await loadBlob(doc.file_id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = doc.name || `payment-${props.payment.id}`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать документ')
  } finally {
    busyKey.value = null
  }
}

function closePreview(): void {
  previewOpen.value = false
  resetPreview()
}
</script>

<template>
  <div v-if="documents.length" class="opt-pay-docs" :class="{ 'opt-pay-docs--compact': compact }">
    <div v-for="doc in documents" :key="doc.file_id" class="opt-pay-docs__row">
      <span class="opt-pay-docs__name" :title="doc.name || 'Подтверждение оплаты'">
        {{ doc.name || 'Подтверждение оплаты' }}
      </span>
      <div class="opt-pay-docs__actions">
        <NButton
          size="tiny"
          type="primary"
          secondary
          :loading="busyKey === `preview:${doc.file_id}`"
          @click.stop="onPreview(doc)"
        >
          <template #icon><Eye :size="12" /></template>
          Просмотр
        </NButton>
        <NButton
          size="tiny"
          secondary
          :loading="busyKey === `dl:${doc.file_id}`"
          @click.stop="onDownload(doc)"
        >
          <template #icon><Download :size="12" /></template>
          Скачать
        </NButton>
      </div>
    </div>
  </div>
  <span v-else class="opt-pay-docs__empty">без документа</span>

  <AttachmentPreviewModal
    :open="previewOpen"
    :loading="previewLoading"
    :label="previewName"
    :blob-url="previewBlobUrl"
    :blob="previewBlob"
    :preview-kind="previewKind"
    @close="closePreview"
  />
</template>

<style scoped>
.opt-pay-docs {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.opt-pay-docs__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}
.opt-pay-docs__name {
  font-size: 0.8rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.opt-pay-docs__actions {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
}
.opt-pay-docs__empty {
  font-size: 0.75rem;
  color: var(--app-text-muted);
}
</style>
