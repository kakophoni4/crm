<script setup lang="ts">
import { NButton, NSelect, NSpin, useMessage } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import {
  probeOptChatAttachment,
  uploadOptFromChatAttachment,
} from '@/features/leads/opt-api'
import type { OptAttachmentProbeResult, OptVatRatePercent } from '@/features/leads/opt-types'
import { useChatsStore } from '@/features/chats/store'
import { resolveAttachmentPreviewKind } from '@/shared/lib/attachment-preview-kind'
import { AppError } from '@/shared/api/http'

const props = defineProps<{
  chatId?: number | null
  messageId: number
  attachmentIndex: number
  attachment: unknown
}>()

const store = useChatsStore()
const message = useMessage()

const probing = ref(false)
const submitting = ref(false)
const probeResult = ref<OptAttachmentProbeResult | null>(null)
const vatRatePercent = ref<OptVatRatePercent>(22)
const vatRateOptions = [
  { label: 'НДС 22%', value: 22 as OptVatRatePercent },
  { label: 'НДС 20%', value: 20 as OptVatRatePercent },
]

const attachmentRow = computed(() => props.attachment as Record<string, unknown>)
const isSpreadsheet = computed(
  () => resolveAttachmentPreviewKind(attachmentRow.value) === 'spreadsheet',
)
const isReady = computed(() => String(attachmentRow.value.status ?? '') === 'ready')
const leadId = computed(() => store.selectedLeadId)

const canScan = computed(
  () =>
    props.chatId != null &&
    leadId.value != null &&
    isSpreadsheet.value &&
    isReady.value,
)

const existingOrder = computed(() => probeResult.value?.existing_order ?? null)
const isApplication = computed(() => probeResult.value?.is_application === true)

async function runProbe(): Promise<void> {
  if (!canScan.value || props.chatId == null || leadId.value == null) {
    probeResult.value = null
    return
  }
  probing.value = true
  try {
    probeResult.value = await probeOptChatAttachment(leadId.value, {
      chat_id: props.chatId,
      message_id: props.messageId,
      attachment_index: props.attachmentIndex,
    })
  } catch {
    probeResult.value = null
  } finally {
    probing.value = false
  }
}

async function submitApplication(): Promise<void> {
  if (!canScan.value || props.chatId == null || leadId.value == null) return
  submitting.value = true
  try {
    await uploadOptFromChatAttachment(leadId.value, {
      chat_id: props.chatId,
      message_id: props.messageId,
      attachment_index: props.attachmentIndex,
      vat_rate_percent: vatRatePercent.value,
    })
    message.success(`Заявка отправлена в обработку (НДС ${vatRatePercent.value}%)`)
    store.bumpOptOrdersRefresh()
    await runProbe()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось отправить заявку')
    await runProbe()
  } finally {
    submitting.value = false
  }
}

watch(
  () => [canScan.value, props.messageId, props.attachmentIndex, leadId.value] as const,
  () => {
    void runProbe()
  },
  { immediate: true },
)
</script>

<template>
  <div v-if="canScan" class="opt-attachment-bar">
    <NSpin v-if="probing && !probeResult" size="small" />
    <template v-else-if="existingOrder">
      <p class="opt-attachment-bar__note">
        Такая заявка уже существует по сделке №{{ existingOrder.lead_id }},
        заявка №{{ existingOrder.order_no }}
      </p>
    </template>
    <template v-else-if="isApplication">
      <p v-if="probeResult?.line_count" class="opt-attachment-bar__hint">
        Распознана заявка: {{ probeResult.line_count }}
        {{ probeResult.line_count === 1 ? 'строка' : 'строк' }}
        <span v-if="probeResult.buyer_inn">, покупатель ИНН {{ probeResult.buyer_inn }}</span>
      </p>
      <div class="opt-attachment-bar__actions">
        <NSelect
          v-model:value="vatRatePercent"
          size="small"
          :options="vatRateOptions"
          :disabled="submitting"
          style="width: 120px"
        />
        <NButton
          size="small"
          type="primary"
          :loading="submitting"
          @click="submitApplication"
        >
          Отправить заявку
        </NButton>
      </div>
    </template>
  </div>
</template>

<style scoped>
.opt-attachment-bar {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  margin-top: 4px;
}

.opt-attachment-bar__hint,
.opt-attachment-bar__note {
  margin: 0;
  font-size: 0.78rem;
  line-height: 1.35;
}

.opt-attachment-bar__note {
  color: var(--app-text-muted);
}

.opt-attachment-bar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
