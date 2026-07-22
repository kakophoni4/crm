<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import {
  NButton,
  NDataTable,
  NDatePicker,
  NEmpty,
  NForm,
  NFormItem,
  NInputNumber,
  NModal,
  NRadio,
  NRadioGroup,
  NSelect,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  NUpload,
  useMessage,
} from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { computed, h, onUnmounted, ref, watch } from 'vue'

import {
  addOptOrderPayment,
  adjustOptOrderCommission,
  deleteOptOrder,
  deleteOptOrderLine,
  downloadOptPaymentDocument,
  downloadOptRegistry,
  listOptOrders,
  patchOptOrderPeriod,
  sendOptRegistryToClient,
  uploadOptApplication,
} from '@/features/leads/opt-api'
import { OPT_PERIOD_OPTIONS } from '@/features/leads/order-fields'
import { peekOptOrders, prefetchOptOrders } from '@/features/chats/payments-cache'
import { useChatsStore } from '@/features/chats/store'
import { uploadFile } from '@/features/chats/api'
import { validateOptPaymentDocuments } from '@/features/leads/opt-payment-validation'
import type { OptOrder, OptOrderLine, OptVatRatePercent } from '@/features/leads/opt-types'
import {
  OPT_PAYMENT_RECIPIENT_OPTIONS,
  OPT_PAYMENT_TYPE_OPTIONS,
  optPaymentRecipientLabel,
  optPaymentStatusLabel,
  optPaymentTypeLabel,
} from '@/features/leads/opt-types'
import { AppError } from '@/shared/api/http'

const props = defineProps<{
  leadId: number | null
  disabled?: boolean
  /** Prefer selecting this order after load (e.g. from applications list). */
  initialOrderId?: number | null
  /** side = chat pane; wide = applications / full modal */
  layout?: 'side' | 'wide'
}>()

const isWide = computed(() => props.layout === 'wide')

const emit = defineEmits<{
  paymentsChanged: []
}>()

const message = useMessage()
const store = useChatsStore()
const loading = ref(false)
const uploading = ref(false)
const deletingId = ref<number | null>(null)
const downloadingId = ref<number | null>(null)
const sendingId = ref<number | null>(null)
const savingPeriodId = ref<number | null>(null)
const periodOptions = OPT_PERIOD_OPTIONS
const orders = ref<OptOrder[]>([])
const selectedOrderId = ref<number | null>(null)
const previewOpen = ref(false)
const previewTab = ref<'application' | 'commission' | 'payments'>('application')
const sendPreviewOpen = ref(false)
const paymentOpen = ref(false)
const commissionOpen = ref(false)
const deleteOpen = ref(false)
const deleteStep = ref<1 | 2>(1)
const deleteTarget = ref<OptOrder | null>(null)
const deleteLineOpen = ref(false)
const deleteLineStep = ref<1 | 2>(1)
const deleteLineTarget = ref<OptOrderLine | null>(null)
const savingPayment = ref(false)
const savingCommission = ref(false)
const deletingLineId = ref<number | null>(null)
const uploadingDocument = ref(false)
const paymentDocuments = ref<{ file_id: number; name: string }[]>([])
const commissionForm = ref({
  direction: 'decrease' as 'increase' | 'decrease',
  amount: null as number | null,
})
const paymentForm = ref({
  amount: null as number | null,
  paid_at: Date.now(),
  payment_type: 'wire' as 'card' | 'crypto' | 'wire' | 'cash',
  recipient: 'orange' as 'orange' | 'beneficiary',
})
const vatRatePercent = ref<OptVatRatePercent>(22)
const vatRateOptions = [
  { label: 'НДС 22%', value: 22 as OptVatRatePercent },
  { label: 'НДС 20%', value: 20 as OptVatRatePercent },
]
let pollTimer: ReturnType<typeof setInterval> | null = null

const hasLead = computed(() => props.leadId != null && !props.disabled)

const selectedOrder = computed(
  () => orders.value.find((row) => row.id === selectedOrderId.value) ?? null,
)

const selectedPaymentsNewestFirst = computed(() => {
  const order = selectedOrder.value
  if (!order) return []
  return [...order.payments].sort(
    (a, b) => new Date(b.paid_at).getTime() - new Date(a.paid_at).getTime(),
  )
})

const needsPolling = computed(() =>
  orders.value.some((row) => row.status === 'queued' || row.status === 'submitting'),
)

const hasPendingSubmission = computed(() =>
  orders.value.some(
    (row) => row.status === 'failed' || row.status === 'queued' || row.status === 'submitting',
  ),
)

function canDeleteOrder(_order: OptOrder): boolean {
  return !props.disabled
}

function canAdjustCommission(order: OptOrder): boolean {
  return order.payment_status !== 'paid'
}

function commissionBase(order: OptOrder): number {
  if (order.commission_base != null) return order.commission_base
  const adjustment = order.commission_adjustment ?? 0
  return order.commission_due - adjustment
}

function commissionAdjustment(order: OptOrder): number {
  return order.commission_adjustment ?? 0
}

const commissionPreviewDue = computed(() => {
  const order = selectedOrder.value
  if (!order || commissionForm.value.amount == null || commissionForm.value.amount <= 0) {
    return null
  }
  const delta =
    commissionForm.value.direction === 'increase'
      ? commissionForm.value.amount
      : -commissionForm.value.amount
  return Math.max(0, order.commission_due + delta)
})

const lineColumns = computed<DataTableColumns<OptOrderLine>>(() => [
  { title: '№', key: 'line_no', width: 44 },
  {
    title: 'Поставщик',
    key: 'supplier',
    ellipsis: { tooltip: true },
    render: (row) => row.supplier.name || row.supplier.inn,
  },
  { title: 'Дата', key: 'document_date', width: 96 },
  {
    title: 'Сумма',
    key: 'amount',
    width: 108,
    align: 'right',
    render: (row) => `${formatMoney(row.amount)} ₽`,
  },
  {
    title: 'Док. 1С',
    key: 'document_number',
    width: 110,
    render: (row) =>
      row.document_number
        ? h('span', { class: 'opt-orders__doc-no' }, row.document_number)
        : '—',
  },
  {
    title: '',
    key: 'actions',
    width: 72,
    render: (row) => {
      const order = selectedOrder.value
      if (!order || order.lines.length <= 1 || props.disabled) return null
      return h(
        NButton,
        {
          size: 'tiny',
          type: 'error',
          quaternary: true,
          loading: deletingLineId.value === row.id,
          onClick: () => openDeleteLineModal(row),
        },
        { default: () => 'Удал.' },
      )
    },
  },
])

const previewLineColumns = computed<DataTableColumns<OptOrderLine>>(() =>
  lineColumns.value.filter((col) => !('key' in col) || col.key !== 'actions'),
)

function openPreview(tab: 'application' | 'commission' | 'payments' = 'application'): void {
  previewTab.value = tab
  previewOpen.value = true
}

function paymentTagType(status: string): 'default' | 'success' | 'error' | 'warning' {
  if (status === 'paid') return 'success'
  if (status === 'partial') return 'warning'
  return 'error'
}

function paymentPillClass(status: string): string {
  if (status === 'paid') return 'opt-orders__pill opt-orders__pill--ok'
  if (status === 'partial') return 'opt-orders__pill opt-orders__pill--warn'
  return 'opt-orders__pill opt-orders__pill--danger'
}

function statusPillClass(status: string): string {
  if (status === 'submitted') return 'opt-orders__pill opt-orders__pill--ok'
  if (status === 'failed') return 'opt-orders__pill opt-orders__pill--danger'
  if (status === 'submitting') return 'opt-orders__pill opt-orders__pill--info'
  return 'opt-orders__pill opt-orders__pill--warn'
}

function volumeRows(order: OptOrder): Array<{ key: string; label: string; volume: number; rate: number; commission: number }> {
  return Object.entries(order.volume_by_category || {}).map(([key, row]) => ({
    key,
    label: row.label || key,
    volume: row.volume,
    rate: row.rate_percent,
    commission: row.commission,
  }))
}

function openPaymentModal(order: OptOrder): void {
  paymentForm.value = {
    amount: order.amount_remaining > 0 ? order.amount_remaining : null,
    paid_at: Date.now(),
    payment_type: 'wire',
    recipient: 'orange',
  }
  paymentDocuments.value = []
  paymentOpen.value = true
}

async function onPaymentDocumentUpload(options: { file: UploadFileInfo }): Promise<void> {
  const raw = options.file.file
  if (raw == null) return
  uploadingDocument.value = true
  try {
    const uploaded = await uploadFile(raw)
    paymentDocuments.value = [
      ...paymentDocuments.value,
      {
        file_id: uploaded.id,
        name: uploaded.name ?? raw.name,
      },
    ]
    message.success('Документ прикреплён')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить документ')
  } finally {
    uploadingDocument.value = false
  }
}

function removePaymentDocument(fileId: number): void {
  paymentDocuments.value = paymentDocuments.value.filter((row) => row.file_id !== fileId)
}

async function onSavePayment(): Promise<void> {
  if (!selectedOrder.value || props.leadId == null) return
  if (paymentForm.value.amount == null || paymentForm.value.amount <= 0) {
    message.warning('Укажите сумму оплаты')
    return
  }
  const fileIds = paymentDocuments.value.map((row) => row.file_id)
  const docError = validateOptPaymentDocuments({
    payment_type: paymentForm.value.payment_type,
    document_file_ids: fileIds,
  })
  if (docError) {
    message.warning(docError)
    return
  }
  savingPayment.value = true
  try {
    const updated = await addOptOrderPayment(props.leadId, selectedOrder.value.id, {
      amount: paymentForm.value.amount,
      paid_at: new Date(paymentForm.value.paid_at).toISOString(),
      payment_type: paymentForm.value.payment_type,
      recipient: paymentForm.value.recipient,
      document_file_id: fileIds[0] ?? null,
      document_file_ids: fileIds,
    })
    orders.value = orders.value
      .map((row) => (row.id === updated.id ? updated : row))
      .sort((a, b) => a.order_no - b.order_no)
    paymentOpen.value = false
    paymentDocuments.value = []
    emit('paymentsChanged')
    message.success('Оплата записана')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось записать оплату')
  } finally {
    savingPayment.value = false
  }
}

function openDeleteLineModal(line: OptOrderLine): void {
  if (!selectedOrder.value || props.leadId == null || props.disabled) return
  if (selectedOrder.value.lines.length <= 1) {
    message.warning('Нельзя удалить единственную фактуру — удалите всю заявку')
    return
  }
  deleteLineTarget.value = line
  deleteLineStep.value = 1
  deleteLineOpen.value = true
}

function closeDeleteLineModal(): void {
  deleteLineOpen.value = false
  deleteLineStep.value = 1
  deleteLineTarget.value = null
}

async function onDeleteLine(): Promise<void> {
  const line = deleteLineTarget.value
  if (!selectedOrder.value || props.leadId == null || line == null) return
  deletingLineId.value = line.id
  try {
    const updated = await deleteOptOrderLine(props.leadId, selectedOrder.value.id, line.id)
    orders.value = orders.value
      .map((row) => (row.id === updated.id ? updated : row))
      .sort((a, b) => a.order_no - b.order_no)
    emit('paymentsChanged')
    closeDeleteLineModal()
    message.success('Фактура удалена, сумма пересчитана')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось удалить фактуру')
  } finally {
    deletingLineId.value = null
  }
}

async function onDownloadPaymentDocument(paymentId: number, fileId?: number | null): Promise<void> {
  if (!selectedOrder.value || props.leadId == null) return
  try {
    const blob = await downloadOptPaymentDocument(
      props.leadId,
      selectedOrder.value.id,
      paymentId,
      fileId,
    )
    const payment = selectedOrder.value.payments.find((row) => row.id === paymentId)
    const doc =
      fileId != null
        ? payment?.documents?.find((row) => row.file_id === fileId)
        : payment?.documents?.[0]
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = doc?.name || payment?.document_name || `payment-${paymentId}`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать документ')
  }
}

function statusTagType(status: string): 'default' | 'success' | 'error' | 'warning' | 'info' {
  if (status === 'submitted') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'submitting') return 'info'
  return 'warning'
}

function statusLabel(status: string): string {
  if (status === 'submitted') return 'готов'
  if (status === 'failed') return 'ошибка'
  if (status === 'submitting') return 'в 1С'
  if (status === 'queued') return 'в очереди'
  return 'черновик'
}

function statusHint(status: string): string {
  if (status === 'queued') return ''
  if (status === 'submitting') return 'Отправка в 1С…'
  if (status === 'submitted') return 'Реестр готов — можно скачать или отправить клиенту'
  if (status === 'failed') return 'Ошибка отправки в 1С — удалите заявку и загрузите файл заново'
  return 'Обработка заявки'
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

function orderLabel(order: OptOrder): string {
  return `Заявка ${order.order_no}`
}

function clientMessagePreview(order: OptOrder): string {
  return `Реестр по заявке №${order.order_no} сделки №${order.lead_id}.`
}

function pickSelectedOrder(nextOrders: OptOrder[], preferredId?: number | null): number | null {
  if (!nextOrders.length) return null
  if (preferredId != null && nextOrders.some((row) => row.id === preferredId)) {
    return preferredId
  }
  return nextOrders[nextOrders.length - 1]?.id ?? null
}

function stopPolling(): void {
  if (pollTimer != null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPolling(): void {
  if (pollTimer != null || !hasLead.value) return
  pollTimer = setInterval(() => {
    void loadOrders({ silent: true })
  }, 2500)
}

async function loadOrders(options?: { silent?: boolean }): Promise<void> {
  if (!hasLead.value || props.leadId == null) {
    orders.value = []
    selectedOrderId.value = null
    stopPolling()
    return
  }
  const leadId = props.leadId
  const cached = peekOptOrders(leadId)
  if (cached?.length && !options?.silent) {
    orders.value = [...cached].sort((a, b) => a.order_no - b.order_no)
    selectedOrderId.value = pickSelectedOrder(
      orders.value,
      selectedOrderId.value ?? props.initialOrderId ?? null,
    )
  }
  if (!options?.silent && !cached?.length) loading.value = true
  try {
    await prefetchOptOrders(leadId, true)
    const fresh = peekOptOrders(leadId)
    const items = fresh ?? (await listOptOrders(leadId))
    orders.value = [...items].sort((a, b) => a.order_no - b.order_no)
    selectedOrderId.value = pickSelectedOrder(
      orders.value,
      selectedOrderId.value ?? props.initialOrderId ?? null,
    )
  } catch (err) {
    if (!options?.silent && !cached?.length) {
      message.error(err instanceof AppError ? err.message : 'Не удалось загрузить заявки')
      orders.value = []
      selectedOrderId.value = null
    }
  } finally {
    if (!options?.silent) loading.value = false
  }
}

async function onUpload(options: { file: UploadFileInfo }): Promise<void> {
  const raw = options.file.file
  if (!hasLead.value || props.leadId == null || raw == null) return
  if (hasPendingSubmission.value) {
    message.warning('Сначала удалите текущую заявку, затем загрузите файл заново')
    return
  }
  uploading.value = true
  try {
    const created = await uploadOptApplication(props.leadId, raw, vatRatePercent.value)
    orders.value = [...orders.value.filter((row) => row.id !== created.id), created].sort(
      (a, b) => a.order_no - b.order_no,
    )
    selectedOrderId.value = created.id
    startPolling()
    message.success(
      `Заявка ${created.order_no} загружена (НДС ${vatRatePercent.value}%) — реестр формируется`,
    )
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить заявку')
  } finally {
    uploading.value = false
  }
}

function openCommissionModal(): void {
  commissionForm.value = {
    direction: 'decrease',
    amount: null,
  }
  commissionOpen.value = true
}

async function onPeriodChange(value: string | null): Promise<void> {
  const order = selectedOrder.value
  if (!order || !value || value === order.period_code || props.disabled) return
  savingPeriodId.value = order.id
  try {
    const updated = await patchOptOrderPeriod(order.id, value)
    orders.value = orders.value.map((row) =>
      row.id === order.id ? { ...row, period_code: updated.period_code } : row,
    )
    message.success('Период сохранён')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить период')
  } finally {
    savingPeriodId.value = null
  }
}

async function onSaveCommission(): Promise<void> {
  if (!selectedOrder.value || props.leadId == null) return
  if (commissionForm.value.amount == null || commissionForm.value.amount <= 0) {
    message.warning('Укажите сумму корректировки')
    return
  }
  savingCommission.value = true
  try {
    const updated = await adjustOptOrderCommission(props.leadId, selectedOrder.value.id, {
      amount: commissionForm.value.amount,
      direction: commissionForm.value.direction,
    })
    orders.value = orders.value
      .map((row) => (row.id === updated.id ? updated : row))
      .sort((a, b) => a.order_no - b.order_no)
    commissionOpen.value = false
    emit('paymentsChanged')
    message.success('Сумма к оплате обновлена')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось изменить сумму к оплате')
  } finally {
    savingCommission.value = false
  }
}

function openDeleteModal(order: OptOrder): void {
  deleteTarget.value = order
  deleteStep.value = 1
  deleteOpen.value = true
}

function closeDeleteModal(): void {
  deleteOpen.value = false
  deleteStep.value = 1
  deleteTarget.value = null
}

async function onDelete(): Promise<void> {
  const order = deleteTarget.value
  if (props.leadId == null || order == null || !canDeleteOrder(order)) return
  deletingId.value = order.id
  try {
    await deleteOptOrder(props.leadId, order.id)
    orders.value = orders.value.filter((row) => row.id !== order.id)
    selectedOrderId.value = pickSelectedOrder(orders.value, null)
    if (!needsPolling.value) stopPolling()
    closeDeleteModal()
    emit('paymentsChanged')
    message.success(`Заявка ${order.order_no} удалена`)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось удалить заявку')
  } finally {
    deletingId.value = null
  }
}

async function onDownload(order: OptOrder): Promise<void> {
  if (props.leadId == null) return
  downloadingId.value = order.id
  try {
    const blob = await downloadOptRegistry(props.leadId, order.id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `реестр-сделка-${order.lead_id}-заявка-${order.order_no}.xlsx`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать реестр')
  } finally {
    downloadingId.value = null
  }
}

async function onSendToClient(order: OptOrder): Promise<void> {
  if (props.leadId == null) return
  sendingId.value = order.id
  try {
    await sendOptRegistryToClient(props.leadId, order.id)
    sendPreviewOpen.value = false
    message.success(`Реестр отправлен клиенту (${clientMessagePreview(order)})`)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось отправить реестр клиенту')
  } finally {
    sendingId.value = null
  }
}

watch(needsPolling, (active) => {
  if (active) startPolling()
  else stopPolling()
})

watch(
  () => [props.leadId, store.optOrdersRefreshNonce, props.initialOrderId] as const,
  () => {
    selectedOrderId.value = null
    stopPolling()
    void loadOrders()
  },
  { immediate: true },
)

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <section class="opt-orders" :class="{ 'opt-orders--wide': isWide }">
    <header class="opt-orders__header">
      <div v-if="!isWide">
        <h3 class="opt-orders__title">
          <template v-if="leadId">Сделка №{{ leadId }} · заявки ОПТ</template>
          <template v-else>Заявки ОПТ</template>
        </h3>
        <p v-if="orders.length" class="opt-orders__count">{{ orders.length }} шт.</p>
      </div>
      <p v-else-if="orders.length" class="opt-orders__count">Заявок: {{ orders.length }}</p>
      <div v-else />
      <div class="opt-orders__upload-row">
        <NSelect
          v-model:value="vatRatePercent"
          size="small"
          :options="vatRateOptions"
          :disabled="!hasLead || uploading || hasPendingSubmission"
          style="width: 120px"
        />
        <NUpload
          :show-file-list="false"
          accept=".xlsx,.xls"
          :disabled="!hasLead || uploading || hasPendingSubmission"
          @change="onUpload"
        >
          <NButton
            size="small"
            type="primary"
            :loading="uploading"
            :disabled="!hasLead || hasPendingSubmission"
          >
            + Заявка
          </NButton>
        </NUpload>
      </div>
    </header>

    <NSpin :show="loading">
      <p v-if="disabled && hasLead" class="opt-orders__hint">
        Сначала выберите период сделки ОПТ — без него заявку загрузить нельзя.
      </p>
      <NEmpty v-if="!orders.length" description="Заявок пока нет" />

      <template v-else>
        <div
          v-if="!isWide || orders.length > 1"
          class="opt-orders__picker"
          role="tablist"
          aria-label="Заявки сделки"
        >
          <button
            v-for="order in orders"
            :key="order.id"
            type="button"
            role="tab"
            class="opt-orders__tab"
            :class="{ 'opt-orders__tab--active': selectedOrderId === order.id }"
            :aria-selected="selectedOrderId === order.id"
            @click="selectedOrderId = order.id"
          >
            <span class="opt-orders__tab-no">{{ orderLabel(order) }}</span>
            <NTag
              size="tiny"
              :bordered="false"
              :class="statusPillClass(order.status)"
            >
              {{ statusLabel(order.status) }}
            </NTag>
          </button>
        </div>

        <article v-if="selectedOrder" class="opt-orders__detail">
          <div class="opt-orders__detail-head">
            <div>
              <strong v-if="!isWide">
                Сделка №{{ selectedOrder.lead_id }} · {{ orderLabel(selectedOrder) }}
              </strong>
              <strong v-else>{{ orderLabel(selectedOrder) }}</strong>
              <span class="opt-orders__meta">
                {{ selectedOrder.source_filename || selectedOrder.crm_id }}
              </span>
            </div>
            <NTag
              size="small"
              :bordered="false"
              :class="statusPillClass(selectedOrder.status)"
            >
              {{ statusLabel(selectedOrder.status) }}
            </NTag>
          </div>

          <p
            v-if="statusHint(selectedOrder.status) && selectedOrder.status !== 'submitted'"
            class="opt-orders__hint"
          >
            {{ statusHint(selectedOrder.status) }}
          </p>

          <dl class="opt-orders__facts">
            <div>
              <dt>Объём</dt>
              <dd>{{ formatMoney(selectedOrder.total_volume) }} ₽</dd>
            </div>
            <div>
              <dt>НДС</dt>
              <dd>{{ selectedOrder.vat_rate_percent ?? 22 }}%</dd>
            </div>
            <div>
              <dt>Период</dt>
              <dd>
                <NSelect
                  :value="selectedOrder.period_code || null"
                  :options="periodOptions"
                  size="small"
                  filterable
                  placeholder="Указать период"
                  :disabled="disabled"
                  :loading="savingPeriodId === selectedOrder.id"
                  style="min-width: 180px"
                  @update:value="(value) => onPeriodChange(value as string | null)"
                />
              </dd>
            </div>
            <div>
              <dt>К оплате</dt>
              <dd>
                {{ formatMoney(selectedOrder.commission_due) }} ₽
                <span
                  v-if="commissionAdjustment(selectedOrder) !== 0"
                  class="opt-orders__adjustment"
                >
                  (база {{ formatMoney(commissionBase(selectedOrder)) }} ₽,
                  {{ commissionAdjustment(selectedOrder) > 0 ? '+' : '' }}{{ formatMoney(commissionAdjustment(selectedOrder)) }} ₽)
                </span>
              </dd>
            </div>
            <div>
              <dt>Оплачено</dt>
              <dd>{{ formatMoney(selectedOrder.amount_paid) }} ₽</dd>
            </div>
            <div>
              <dt>Остаток</dt>
              <dd>{{ formatMoney(selectedOrder.amount_remaining) }} ₽</dd>
            </div>
            <div>
              <dt>Оплата</dt>
              <dd>
                <NTag
                  size="small"
                  :bordered="false"
                  :class="paymentPillClass(selectedOrder.payment_status)"
                >
                  {{ optPaymentStatusLabel(selectedOrder.payment_status) }}
                </NTag>
              </dd>
            </div>
            <div v-if="!isWide">
              <dt>Покупатель</dt>
              <dd>
                <template v-if="selectedOrder.buyer.name">
                  {{ selectedOrder.buyer.name }}
                </template>
                <template v-else>
                  ИНН {{ selectedOrder.buyer.inn }}
                </template>
              </dd>
            </div>
          </dl>

          <div v-if="volumeRows(selectedOrder).length" class="opt-orders__volume">
            <h4 class="opt-orders__subheading">Разбивка по категориям лавок</h4>
            <table class="opt-orders__volume-table">
              <thead>
                <tr>
                  <th>Категория</th>
                  <th>Объём</th>
                  <th>Ставка</th>
                  <th>К оплате</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in volumeRows(selectedOrder)" :key="row.key">
                  <td>{{ row.label }}</td>
                  <td>{{ formatMoney(row.volume) }} ₽</td>
                  <td>{{ row.rate }}%</td>
                  <td>{{ formatMoney(row.commission) }} ₽</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="opt-orders__payments">
            <div class="opt-orders__history-head">
              <h4 class="opt-orders__subheading">
                История оплат
                <span class="opt-orders__meta">
                  ·
                  {{
                    selectedPaymentsNewestFirst.length
                      ? `${selectedPaymentsNewestFirst.length} шт.`
                      : 'пока нет'
                  }}
                </span>
              </h4>
              <NButton size="tiny" quaternary @click="openPreview('payments')">
                Открыть
              </NButton>
            </div>
            <ul v-if="selectedPaymentsNewestFirst.length" class="opt-orders__payments-list">
              <li
                v-for="payment in selectedPaymentsNewestFirst.slice(0, 2)"
                :key="payment.id"
              >
                <div class="opt-orders__payment-main">
                  <strong>{{ formatMoney(payment.amount) }} ₽</strong>
                  <span class="opt-orders__meta">
                    {{ new Date(payment.paid_at).toLocaleString('ru-RU') }} ·
                    {{ optPaymentTypeLabel(payment.payment_type) }} ·
                    {{ payment.created_by_name || `user #${payment.created_by}` }}
                  </span>
                </div>
              </li>
            </ul>
          </div>

          <div
            v-if="selectedOrder.commission_history?.length"
            class="opt-orders__history"
          >
            <div class="opt-orders__history-head">
              <h4 class="opt-orders__subheading">
                История суммы к оплате
                <span class="opt-orders__meta">
                  · {{ selectedOrder.commission_history.length }} изм.
                </span>
              </h4>
              <NButton size="tiny" quaternary @click="openPreview('commission')">
                Открыть
              </NButton>
            </div>
          </div>

          <NDataTable
            size="small"
            :columns="lineColumns"
            :data="selectedOrder.lines"
            :bordered="false"
            :pagination="false"
            :max-height="isWide ? 240 : 200"
            :scroll-x="720"
            class="opt-orders__table"
          />

          <p v-if="selectedOrder.submission_error" class="opt-orders__error">
            {{ selectedOrder.submission_error }}
          </p>

          <div class="opt-orders__actions">
            <NButton
              v-if="selectedOrder.payment_status !== 'paid'"
              size="small"
              type="primary"
              secondary
              @click="openPaymentModal(selectedOrder)"
            >
              Записать оплату
            </NButton>

            <NButton size="small" secondary @click="openPreview()">
              Предпросмотр
            </NButton>

            <NButton
              v-if="selectedOrder.status === 'submitted'"
              size="small"
              secondary
              :loading="downloadingId === selectedOrder.id"
              @click="onDownload(selectedOrder)"
            >
              Скачать реестр
            </NButton>

            <NButton
              v-if="selectedOrder.status === 'submitted'"
              size="small"
              type="primary"
              secondary
              @click="sendPreviewOpen = true"
            >
              Отправить клиенту
            </NButton>

            <NButton
              v-if="canAdjustCommission(selectedOrder)"
              size="small"
              secondary
              @click="openCommissionModal()"
            >
              Изменить к оплате
            </NButton>

            <NButton
              v-if="canDeleteOrder(selectedOrder)"
              size="small"
              type="error"
              secondary
              :loading="deletingId === selectedOrder.id"
              @click="openDeleteModal(selectedOrder)"
            >
              Удалить заявку
            </NButton>
          </div>
        </article>
      </template>
    </NSpin>

    <NModal
      v-model:show="previewOpen"
      preset="card"
      :title="selectedOrder ? `Предпросмотр · ${orderLabel(selectedOrder)}` : 'Предпросмотр'"
      style="max-width: 720px"
    >
      <template v-if="selectedOrder">
        <NTabs v-model:value="previewTab" type="line" size="small" animated>
          <NTabPane name="application" tab="Заявка">
            <p class="opt-orders__preview-text">{{ clientMessagePreview(selectedOrder) }}</p>
            <NDataTable
              size="small"
              :columns="previewLineColumns"
              :data="selectedOrder.lines"
              :bordered="true"
              :pagination="false"
              :max-height="360"
            />
          </NTabPane>

          <NTabPane name="commission" tab="История суммы к оплате">
            <ul
              v-if="selectedOrder.commission_history?.length"
              class="opt-orders__history-list"
            >
              <li v-for="item in selectedOrder.commission_history" :key="item.id">
                <span>
                  {{ formatMoney(item.old_commission_due) }} →
                  {{ formatMoney(item.new_commission_due) }} ₽
                  ({{ item.direction === 'decrease' ? 'скидка' : 'доначисление' }}
                  {{ formatMoney(Math.abs(item.delta)) }} ₽)
                </span>
                <span class="opt-orders__meta">
                  {{ item.changed_by_name || `user #${item.changed_by}` }} ·
                  {{ new Date(item.created_at).toLocaleString('ru-RU') }}
                </span>
              </li>
            </ul>
            <NEmpty v-else description="Изменений суммы пока нет" />
          </NTabPane>

          <NTabPane name="payments" tab="История оплат">
            <ul v-if="selectedPaymentsNewestFirst.length" class="opt-orders__payments-list">
              <li v-for="payment in selectedPaymentsNewestFirst" :key="payment.id">
                <div class="opt-orders__payment-main">
                  <strong>{{ formatMoney(payment.amount) }} ₽</strong>
                  <span class="opt-orders__meta">
                    {{ new Date(payment.paid_at).toLocaleString('ru-RU') }} ·
                    {{ optPaymentTypeLabel(payment.payment_type) }} ·
                    {{ optPaymentRecipientLabel(payment.recipient) }}
                  </span>
                  <span class="opt-orders__meta">
                    внёс: {{ payment.created_by_name || `user #${payment.created_by}` }}
                  </span>
                </div>
                <div class="opt-orders__payment-docs">
                  <template v-if="(payment.documents?.length || 0) > 0">
                    <NButton
                      v-for="doc in payment.documents"
                      :key="doc.file_id"
                      size="tiny"
                      quaternary
                      @click="onDownloadPaymentDocument(payment.id, doc.file_id)"
                    >
                      {{ doc.name || 'Документ' }}
                    </NButton>
                  </template>
                  <NButton
                    v-else-if="payment.document_file_id"
                    size="tiny"
                    quaternary
                    @click="onDownloadPaymentDocument(payment.id)"
                  >
                    {{ payment.document_name || 'Документ' }}
                  </NButton>
                  <span v-else class="opt-orders__meta">без документа</span>
                </div>
              </li>
            </ul>
            <NEmpty v-else description="Оплат пока нет" />
          </NTabPane>
        </NTabs>
      </template>
    </NModal>

    <NModal
      v-model:show="sendPreviewOpen"
      preset="card"
      title="Отправить реестр клиенту"
      style="max-width: 520px"
    >
      <template v-if="selectedOrder">
        <p class="opt-orders__preview-text">
          Клиенту уйдёт сообщение в чат с файлом реестра:
        </p>
        <blockquote class="opt-orders__quote">{{ clientMessagePreview(selectedOrder) }}</blockquote>
        <p class="opt-orders__meta">
          Файл: реестр-сделка-{{ selectedOrder.lead_id }}-заявка-{{ selectedOrder.order_no }}.xlsx
        </p>
      </template>
      <template #footer>
        <div class="opt-orders__modal-footer">
          <NButton @click="sendPreviewOpen = false">Отмена</NButton>
          <NButton
            type="primary"
            :loading="sendingId === selectedOrder?.id"
            :disabled="!selectedOrder"
            @click="selectedOrder && onSendToClient(selectedOrder)"
          >
            Отправить
          </NButton>
        </div>
      </template>
    </NModal>

    <NModal
      v-model:show="deleteLineOpen"
      preset="card"
      title="Удалить фактуру"
      style="max-width: 460px"
      @after-leave="closeDeleteLineModal"
    >
      <template v-if="deleteLineTarget">
        <template v-if="deleteLineStep === 1">
          <p class="opt-orders__preview-text">
            Удалить фактуру №{{ deleteLineTarget.line_no }}
            <template v-if="deleteLineTarget.document_number">
              ({{ deleteLineTarget.document_number }})
            </template>
            на сумму {{ formatMoney(deleteLineTarget.amount) }} ₽?
          </p>
          <p class="opt-orders__meta">
            Поставщик:
            {{
              deleteLineTarget.supplier.name ||
              `ИНН ${deleteLineTarget.supplier.inn}`
            }}
          </p>
          <p class="opt-orders__meta">
            После удаления сумма к оплате по заявке будет пересчитана.
          </p>
        </template>
        <template v-else>
          <p class="opt-orders__preview-text">
            Подтвердите удаление. Это действие необратимо.
          </p>
          <p class="opt-orders__meta opt-orders__meta--warning">
            Фактура №{{ deleteLineTarget.line_no }} ·
            {{ formatMoney(deleteLineTarget.amount) }} ₽ будет удалена без восстановления.
          </p>
        </template>
      </template>
      <template #footer>
        <div class="opt-orders__modal-footer">
          <NButton @click="closeDeleteLineModal">Отмена</NButton>
          <NButton v-if="deleteLineStep === 1" type="warning" @click="deleteLineStep = 2">
            Продолжить
          </NButton>
          <NButton
            v-else
            type="error"
            :loading="deleteLineTarget != null && deletingLineId === deleteLineTarget.id"
            @click="void onDeleteLine()"
          >
            Удалить безвозвратно
          </NButton>
        </div>
      </template>
    </NModal>

    <NModal
      v-model:show="deleteOpen"
      preset="card"
      :title="deleteTarget ? `Удалить ${orderLabel(deleteTarget)}` : 'Удалить заявку'"
      style="max-width: 460px"
      @after-leave="closeDeleteModal"
    >
      <template v-if="deleteTarget">
        <template v-if="deleteStep === 1">
          <p class="opt-orders__preview-text">
            Удалить заявку {{ orderLabel(deleteTarget) }} по сделке №{{ deleteTarget.lead_id }}?
          </p>
          <p class="opt-orders__meta">
            Файл: {{ deleteTarget.source_filename || deleteTarget.crm_id }}
          </p>
          <p v-if="deleteTarget.lines.length === 1" class="opt-orders__meta">
            В заявке одна фактура — её нельзя удалить отдельно, удаляется вся заявка.
          </p>
          <p
            v-if="deleteTarget.payments.length"
            class="opt-orders__meta opt-orders__meta--warning"
          >
            В заявке {{ deleteTarget.payments.length }}
            {{
              deleteTarget.payments.length === 1
                ? 'оплата'
                : deleteTarget.payments.length < 5
                  ? 'оплаты'
                  : 'оплат'
            }}
            — они тоже будут удалены.
          </p>
          <p v-if="deleteTarget.status === 'submitted'" class="opt-orders__meta opt-orders__meta--warning">
            Заявка уже отправлена в 1С. Удаление затронет только CRM — запись в 1С останется.
          </p>
        </template>
        <template v-else>
          <p class="opt-orders__preview-text">
            Это действие необратимо. Заявка, фактуры
            <template v-if="deleteTarget.payments.length"> и оплаты</template>
            будут удалены без восстановления.
          </p>
          <p v-if="deleteTarget.status === 'submitted'" class="opt-orders__meta opt-orders__meta--warning">
            Запись в 1С не удаляется автоматически.
          </p>
        </template>
      </template>
      <template #footer>
        <div class="opt-orders__modal-footer">
          <NButton @click="closeDeleteModal">Отмена</NButton>
          <NButton v-if="deleteStep === 1" type="warning" @click="deleteStep = 2">
            Продолжить
          </NButton>
          <NButton
            v-else
            type="error"
            :loading="deleteTarget != null && deletingId === deleteTarget.id"
            @click="void onDelete()"
          >
            Удалить безвозвратно
          </NButton>
        </div>
      </template>
    </NModal>

    <NModal
      v-model:show="commissionOpen"
      preset="card"
      title="Изменить сумму к оплате"
      style="max-width: 440px"
    >
      <template v-if="selectedOrder">
        <p class="opt-orders__preview-text">
          Базовая сумма: {{ formatMoney(commissionBase(selectedOrder)) }} ₽
        </p>
        <p v-if="commissionAdjustment(selectedOrder) !== 0" class="opt-orders__meta">
          Текущая корректировка:
          {{ commissionAdjustment(selectedOrder) > 0 ? '+' : '' }}{{ formatMoney(commissionAdjustment(selectedOrder)) }} ₽
        </p>
        <NForm label-placement="top">
          <NFormItem label="Тип корректировки">
            <NRadioGroup v-model:value="commissionForm.direction">
              <NSpace>
                <NRadio value="decrease">Скидка (−)</NRadio>
                <NRadio value="increase">Доначисление (+)</NRadio>
              </NSpace>
            </NRadioGroup>
          </NFormItem>
          <NFormItem label="Сумма">
            <NInputNumber
              v-model:value="commissionForm.amount"
              :min="0.01"
              :precision="2"
              class="opt-orders__number"
            />
          </NFormItem>
        </NForm>
        <p v-if="commissionPreviewDue != null" class="opt-orders__preview-text">
          К оплате станет: <strong>{{ formatMoney(commissionPreviewDue) }} ₽</strong>
        </p>
      </template>
      <template #footer>
        <div class="opt-orders__modal-footer">
          <NButton @click="commissionOpen = false">Отмена</NButton>
          <NButton type="primary" :loading="savingCommission" @click="onSaveCommission">
            Применить
          </NButton>
        </div>
      </template>
    </NModal>

    <NModal v-model:show="paymentOpen" preset="card" title="Записать оплату" style="max-width: 420px">
      <NForm label-placement="top">
        <NFormItem label="Сумма оплаты">
          <NInputNumber
            v-model:value="paymentForm.amount"
            :min="0.01"
            :precision="2"
            class="opt-orders__number"
          />
        </NFormItem>
        <NFormItem label="Когда оплачено">
          <NDatePicker v-model:value="paymentForm.paid_at" type="datetime" style="width: 100%" />
        </NFormItem>
        <NFormItem label="Тип оплаты">
          <NSelect v-model:value="paymentForm.payment_type" :options="OPT_PAYMENT_TYPE_OPTIONS" />
        </NFormItem>
        <NFormItem label="Кому">
          <NSelect v-model:value="paymentForm.recipient" :options="OPT_PAYMENT_RECIPIENT_OPTIONS" />
        </NFormItem>
        <NFormItem label="Платёжные документы">
          <div class="opt-orders__doc-upload">
            <NUpload
              :show-file-list="false"
              multiple
              accept=".pdf,.png,.jpg,.jpeg,.webp,.heic"
              :disabled="uploadingDocument"
              @change="onPaymentDocumentUpload"
            >
              <NButton size="small" :loading="uploadingDocument">
                Добавить чек / ПП / скрин
              </NButton>
            </NUpload>
            <ul v-if="paymentDocuments.length" class="opt-orders__doc-list">
              <li v-for="doc in paymentDocuments" :key="doc.file_id">
                <span>{{ doc.name }}</span>
                <NButton size="tiny" quaternary type="error" @click="removePaymentDocument(doc.file_id)">
                  Убрать
                </NButton>
              </li>
            </ul>
            <p v-else class="opt-orders__meta">
              {{
                paymentForm.payment_type === 'cash'
                  ? 'Для наличных документ не обязателен'
                  : 'Обязательно прикрепите документ подтверждения'
              }}
            </p>
          </div>
        </NFormItem>
      </NForm>
      <template #footer>
        <div class="opt-orders__modal-footer">
          <NButton @click="paymentOpen = false">Отмена</NButton>
          <NButton type="primary" :loading="savingPayment" @click="onSavePayment">Сохранить</NButton>
        </div>
      </template>
    </NModal>
  </section>
</template>

<style scoped>
.opt-orders {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.opt-orders--wide {
  gap: 8px;
}

.opt-orders--wide .opt-orders__detail {
  padding: 10px 12px;
  gap: 8px;
}

.opt-orders--wide .opt-orders__facts {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px 12px;
}

.opt-orders--wide .opt-orders__actions {
  position: sticky;
  bottom: 0;
  z-index: 3;
  margin-top: 6px;
  margin-left: -12px;
  margin-right: -12px;
  margin-bottom: -10px;
  padding: 10px 12px;
  border-top: 1px solid var(--app-border);
  background: var(--app-surface);
  box-shadow: 0 -8px 16px color-mix(in srgb, #000 25%, transparent);
}

.opt-orders__pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  line-height: 1.3;
  color: #fff !important;
  background: var(--app-text-muted);
}

.opt-orders__pill--ok {
  background: #1a7f37;
}

.opt-orders__pill--danger {
  background: #cf222e;
}

.opt-orders__pill--warn {
  background: #9a6700;
}

.opt-orders__pill--info {
  background: #0969da;
}

/* Override Naive tag soft colors when our pill class is applied */
.opt-orders__pill.n-tag {
  --n-color: transparent !important;
  --n-text-color: #fff !important;
  border: 0 !important;
}

@media (max-width: 900px) {
  .opt-orders--wide .opt-orders__facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.opt-orders__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.opt-orders__upload-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.opt-orders__title {
  margin: 0;
  font-size: 0.92rem;
  font-weight: 700;
}

.opt-orders__count,
.opt-orders__hint {
  margin: 2px 0 0;
  font-size: 0.75rem;
  color: var(--app-text-muted);
}

.opt-orders__picker {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.opt-orders__tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface, transparent);
  cursor: pointer;
  font-size: 0.8rem;
}

.opt-orders__tab--active {
  border-color: var(--app-accent);
  background: color-mix(in srgb, var(--app-accent) 8%, transparent);
}

.opt-orders__tab-no {
  font-weight: 600;
}

.opt-orders__detail {
  border: 1px solid var(--app-border);
  border-radius: 8px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  overflow: hidden;
}

.opt-orders__detail-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: flex-start;
}

.opt-orders__meta {
  display: block;
  font-size: 0.75rem;
  color: var(--app-text-muted);
  margin-top: 2px;
  word-break: break-all;
}

.opt-orders__meta--warning {
  color: var(--n-warning-color);
  margin-top: 8px;
}

.opt-orders__facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
  margin: 0;
  font-size: 0.8rem;
  align-items: start;
}

.opt-orders__facts div {
  min-width: 0;
  display: grid;
  grid-template-columns: 1fr;
  gap: 2px;
}

.opt-orders__facts dt {
  margin: 0;
  color: var(--app-text-muted);
  font-size: 0.72rem;
}

.opt-orders__facts dd {
  margin: 2px 0 0;
}

.opt-orders__table :deep(.n-data-table-th) {
  font-size: 0.72rem;
}

.opt-orders__table :deep(.n-data-table-td) {
  font-size: 0.78rem;
  vertical-align: top;
  word-break: break-word;
}

.opt-orders__table {
  width: 100%;
  min-width: 0;
}

.opt-orders__doc-no {
  color: var(--app-accent);
  font-weight: 600;
}

.opt-orders__error {
  margin: 0;
  color: var(--app-danger);
  font-size: 0.8rem;
}

.opt-orders__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.opt-orders__actions :deep(.n-button) {
  min-height: 28px;
  padding: 0 12px;
}

.opt-orders__preview-text {
  margin: 0 0 12px;
  font-size: 0.85rem;
}

.opt-orders__quote {
  margin: 0 0 12px;
  padding: 10px 12px;
  border-left: 3px solid var(--app-accent);
  background: var(--app-surface-elevated);
  font-size: 0.9rem;
}

.opt-orders__modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.opt-orders__subheading {
  margin: 0 0 6px;
  font-size: 0.82rem;
  font-weight: 700;
}

.opt-orders__volume-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.78rem;
}

.opt-orders__volume-table th,
.opt-orders__volume-table td {
  padding: 4px 6px;
  border-bottom: 1px solid var(--app-border);
  text-align: left;
}

.opt-orders__volume-table th:last-child,
.opt-orders__volume-table td:last-child {
  text-align: right;
}

.opt-orders__payments-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 0.78rem;
}

.opt-orders__payments-list li {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
}

.opt-orders__payment-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.opt-orders__payment-main .opt-orders__meta {
  margin-top: 0;
}

.opt-orders__payment-docs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.opt-orders__history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.opt-orders__history-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 0.78rem;
}

.opt-orders__history-list li {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.opt-orders__doc-upload {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.opt-orders__doc-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.opt-orders__doc-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 0.8rem;
}

.opt-orders__adjustment {
  display: block;
  margin-top: 2px;
  font-size: 0.72rem;
  color: var(--app-text-muted);
}

.opt-orders__number {
  width: 100%;
}
</style>
