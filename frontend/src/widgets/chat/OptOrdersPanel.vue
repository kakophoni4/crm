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
import { computed, h, onMounted, onUnmounted, ref, watch } from 'vue'

import {
  addOptOrderPayment,
  adjustOptOrderCommission,
  deleteOptOrder,
  deleteOptOrderLine,
  downloadOptOrderReceiptsArchive,
  downloadOptOrderSalesBooksArchive,
  downloadOptRegistry,
  listOptOrderReceipts,
  listOptOrderSalesBookExtracts,
  listOptOrders,
  patchOptOrderPeriod,
  sendOptOrderReceiptsToClient,
  sendOptOrderSalesBooksToClient,
  sendOptRegistryToClient,
  uploadOptApplication,
} from '@/features/leads/opt-api'
import { OPT_PERIOD_OPTIONS, optVatRateForPeriod } from '@/features/leads/order-fields'
import {
  invalidateOrderDocsAvailability,
  loadOrderDocsAvailability,
  peekOrderDocsAvailability,
  setOrderDocsAvailability,
} from '@/features/leads/order-docs-availability-cache'
import { setOptOrdersCache } from '@/features/chats/chats-disk-cache'
import { peekOptOrders } from '@/features/chats/payments-cache'
import { useChatsStore } from '@/features/chats/store'
import { uploadFile } from '@/features/chats/api'
import { validateOptPaymentDocuments } from '@/features/leads/opt-payment-validation'
import type { OptOrder, OptOrderLine } from '@/features/leads/opt-types'
import {
  OPT_PAYMENT_RECIPIENT_OPTIONS,
  OPT_PAYMENT_TYPE_OPTIONS,
  optPaymentRecipientLabel,
  optPaymentStatusLabel,
  optPaymentTypeLabel,
} from '@/features/leads/opt-types'
import { AppError } from '@/shared/api/http'
import OptPaymentDocuments from '@/widgets/chat/OptPaymentDocuments.vue'

const props = defineProps<{
  leadId: number | null
  disabled?: boolean
  /** Prefer selecting this order after load (e.g. from applications list). */
  initialOrderId?: number | null
  /** side = chat pane; wide = compact modal; page = full applications screen */
  layout?: 'side' | 'wide' | 'page'
}>()

const isPage = computed(() => props.layout === 'page')
const isWide = computed(() => props.layout === 'wide' || isPage.value)

const emit = defineEmits<{
  paymentsChanged: []
  select: [order: OptOrder]
}>()

const message = useMessage()
const store = useChatsStore()
const loading = ref(false)
const uploading = ref(false)
const deletingId = ref<number | null>(null)
const downloadingId = ref<number | null>(null)
const downloadingReceiptsId = ref<number | null>(null)
const sendingReceiptsId = ref<number | null>(null)
const receiptsAvailable = ref(false)
const sendReceiptsOpen = ref(false)
const downloadingSalesBooksId = ref<number | null>(null)
const sendingSalesBooksId = ref<number | null>(null)
const salesBooksAvailable = ref(false)
const sendSalesBooksOpen = ref(false)
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
let pollTimer: ReturnType<typeof setInterval> | null = null
let tabVisible = typeof document !== 'undefined' ? !document.hidden : true
let loadAbort: AbortController | null = null
let loadSeq = 0

function isAbortError(err: unknown): boolean {
  if (err instanceof DOMException && err.name === 'AbortError') return true
  return (
    typeof err === 'object'
    && err != null
    && 'code' in err
    && (err as { code: string }).code === 'ERR_CANCELED'
  )
}

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
  // Soft-delete on API; double-confirm modal. Allowed for any status when lead is editable.
  return !props.disabled
}

function canAdjustCommission(order: OptOrder): boolean {
  return order.payment_status !== 'paid'
}

function isBenik(order: OptOrder): boolean {
  return order.order_kind === 'benik'
}

function canRecordPayment(order: OptOrder): boolean {
  if (order.payment_status === 'paid') return false
  if (isBenik(order) && Number(order.commission_due) <= 0) return false
  return true
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

function paymentPillClass(status: string): string {
  if (status === 'paid') return 'opt-orders__pill opt-orders__pill--ok'
  if (status === 'partial') return 'opt-orders__pill opt-orders__pill--warn'
  return 'opt-orders__pill opt-orders__pill--danger'
}

function statusPillClass(order: OptOrder | string): string {
  if (typeof order !== 'string') {
    if (order.payment_status === 'paid') return 'opt-orders__pill opt-orders__pill--ok'
    if (order.payment_status === 'partial') return 'opt-orders__pill opt-orders__pill--warn'
    if (order.receipts_sent_at && order.status === 'submitted') {
      return 'opt-orders__pill opt-orders__pill--warn'
    }
  }
  const status = typeof order === 'string' ? order : order.status
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
    amount: order.amount_remaining > 0 ? Math.round(order.amount_remaining) : null,
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

function statusLabel(order: OptOrder | string): string {
  if (typeof order !== 'string') {
    if (order.payment_status === 'paid') return 'оплачена'
    if (order.payment_status === 'partial') return 'частично'
    if (isBenik(order)) return 'Беник'
    if (order.receipts_sent_at && order.status === 'submitted') return 'сбор оплат'
  }
  const status = typeof order === 'string' ? order : order.status
  if (status === 'submitted') return 'готов'
  if (status === 'failed') return 'ошибка'
  if (status === 'submitting') return 'в 1С'
  if (status === 'queued') return 'в очереди'
  if (status === 'ready') return 'Беник'
  return 'черновик'
}

function statusHint(order: OptOrder | string): string {
  if (typeof order !== 'string') {
    if (isBenik(order) && Number(order.commission_due) <= 0) {
      return 'Заявка без 1С и реестра — укажите сумму к оплате'
    }
    if (order.payment_status === 'paid') return 'Комиссия по заявке полностью оплачена'
    if (order.payment_status === 'partial') return 'Частичная оплата — остаток ещё не закрыт'
    if (isBenik(order)) return 'Заявка без 1С и реестра'
    if (order.receipts_sent_at && order.status === 'submitted') {
      return 'Квитанции отправлены клиенту — ожидаем сбор оплат'
    }
  }
  const status = typeof order === 'string' ? order : order.status
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

/** Commission / payments — whole rubles, no kopecks. */
function formatRubles(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Math.round(value))
}

function orderLabel(order: OptOrder): string {
  return isBenik(order) ? `Беник ${order.order_no}` : `Заявка ${order.order_no}`
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

function syncPolling(): void {
  if (needsPolling.value && tabVisible && hasLead.value) startPolling()
  else stopPolling()
}

function startPolling(): void {
  if (pollTimer != null || !hasLead.value || !tabVisible) return
  pollTimer = setInterval(() => {
    void loadOrders({ silent: true })
  }, 20_000)
}

function onVisibilityChange(): void {
  tabVisible = !document.hidden
  if (tabVisible) {
    syncPolling()
    if (needsPolling.value && hasLead.value) void loadOrders({ silent: true })
  } else {
    stopPolling()
    loadAbort?.abort()
  }
}

async function loadOrders(options?: { silent?: boolean }): Promise<void> {
  if (!hasLead.value || props.leadId == null) {
    orders.value = []
    selectedOrderId.value = null
    stopPolling()
    return
  }
  if (options?.silent && !tabVisible) return
  const leadId = props.leadId
  loadAbort?.abort()
  loadAbort = new AbortController()
  const signal = loadAbort.signal
  const seq = ++loadSeq
  const cached = peekOptOrders(leadId)
  if (cached?.length && !options?.silent) {
    orders.value = [...cached].sort((a, b) => a.order_no - b.order_no)
    selectedOrderId.value = pickSelectedOrder(
      orders.value,
      selectedOrderId.value ?? props.initialOrderId ?? null,
    )
  }
  if (!options?.silent && !cached?.length && orders.value.length === 0) loading.value = true
  try {
    const items = await listOptOrders(leadId, { signal })
    if (signal.aborted || seq !== loadSeq || props.leadId !== leadId) return
    setOptOrdersCache(leadId, items)
    orders.value = [...items].sort((a, b) => a.order_no - b.order_no)
    selectedOrderId.value = pickSelectedOrder(
      orders.value,
      selectedOrderId.value ?? props.initialOrderId ?? null,
    )
    // Selection may stay the same (single order) — still re-check docs.
    void refreshReceiptsAvailability({ force: !options?.silent })
  } catch (err) {
    if (signal.aborted || isAbortError(err)) return
    if (!options?.silent && !cached?.length && orders.value.length === 0) {
      message.error(err instanceof AppError ? err.message : 'Не удалось загрузить заявки')
      orders.value = []
      selectedOrderId.value = null
    }
  } finally {
    if (!options?.silent && seq === loadSeq) loading.value = false
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
    const created = await uploadOptApplication(props.leadId, raw)
    orders.value = [...orders.value.filter((row) => row.id !== created.id), created].sort(
      (a, b) => a.order_no - b.order_no,
    )
    selectedOrderId.value = created.id
    syncPolling()
    message.success(
      `Заявка ${created.order_no} загружена (НДС ${created.vat_rate_percent ?? optVatRateForPeriod(created.period_code)}%) — реестр формируется`,
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


async function refreshReceiptsAvailability(opts?: { force?: boolean }): Promise<void> {
  if (props.leadId == null || selectedOrderId.value == null) {
    receiptsAvailable.value = false
    salesBooksAvailable.value = false
    return
  }
  const order = orders.value.find((row) => row.id === selectedOrderId.value)
  if (!order || order.status !== 'submitted') {
    receiptsAvailable.value = false
    salesBooksAvailable.value = false
    return
  }
  const leadId = props.leadId
  const orderId = order.id
  // Уже отправляли квитанции клиенту — кнопки показываем сразу.
  if (order.receipts_sent_at) {
    receiptsAvailable.value = true
  }
  // Мгновенно показываем кэш — не мигаем кнопками «нет → есть».
  const cached = peekOrderDocsAvailability(orderId)
  if (cached) {
    if (cached.receipts) receiptsAvailable.value = true
    else if (!order.receipts_sent_at) receiptsAvailable.value = false
    salesBooksAvailable.value = cached.salesBooks
    // Ложный «нет» при уже отправленных квитанциях — сбрасываем кэш.
    if (!cached.receipts && order.receipts_sent_at) {
      invalidateOrderDocsAvailability(orderId)
    }
  }
  const force =
    opts?.force ||
    (!!order.receipts_sent_at && cached != null && !cached.receipts)
  try {
    const value = await loadOrderDocsAvailability(
      orderId,
      async () => {
        const [receiptsRes, booksRes] = await Promise.allSettled([
          listOptOrderReceipts(leadId, orderId),
          listOptOrderSalesBookExtracts(leadId, orderId),
        ])
        if (receiptsRes.status === 'rejected' && booksRes.status === 'rejected') {
          throw receiptsRes.reason
        }
        const receipts =
          receiptsRes.status === 'fulfilled'
            ? receiptsRes.value.available
            : Boolean(order.receipts_sent_at)
        const salesBooks =
          booksRes.status === 'fulfilled' ? booksRes.value.available : false
        return { receipts, salesBooks }
      },
      { force },
    )
    if (selectedOrderId.value === orderId) {
      receiptsAvailable.value = value.receipts || Boolean(order.receipts_sent_at)
      salesBooksAvailable.value = value.salesBooks
    }
  } catch {
    if (selectedOrderId.value === orderId) {
      if (order.receipts_sent_at) receiptsAvailable.value = true
      else if (!cached) receiptsAvailable.value = false
      if (!cached) salesBooksAvailable.value = false
    }
  }
}

async function onDownloadReceipts(order: OptOrder): Promise<void> {
  if (props.leadId == null) return
  downloadingReceiptsId.value = order.id
  try {
    const blob = await downloadOptOrderReceiptsArchive(props.leadId, order.id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `квитанции-сделка-${order.lead_id}-заявка-${order.order_no}.zip`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать квитанции')
  } finally {
    downloadingReceiptsId.value = null
  }
}

async function onSendReceiptsToClient(order: OptOrder): Promise<void> {
  if (props.leadId == null) return
  sendingReceiptsId.value = order.id
  try {
    await sendOptOrderReceiptsToClient(props.leadId, order.id)
    sendReceiptsOpen.value = false
    orders.value = orders.value.map((row) =>
      row.id === order.id
        ? { ...row, receipts_sent_at: row.receipts_sent_at || new Date().toISOString() }
        : row,
    )
    setOrderDocsAvailability(order.id, {
      receipts: true,
      salesBooks: salesBooksAvailable.value,
    })
    message.success('Квитанции отправлены клиенту')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось отправить квитанции')
  } finally {
    sendingReceiptsId.value = null
  }
}

async function onDownloadSalesBooks(order: OptOrder): Promise<void> {
  if (props.leadId == null) return
  downloadingSalesBooksId.value = order.id
  try {
    const blob = await downloadOptOrderSalesBooksArchive(props.leadId, order.id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `книги-продаж-сделка-${order.lead_id}-заявка-${order.order_no}.zip`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать книги продаж')
  } finally {
    downloadingSalesBooksId.value = null
  }
}

async function onSendSalesBooksToClient(order: OptOrder): Promise<void> {
  if (props.leadId == null) return
  sendingSalesBooksId.value = order.id
  try {
    await sendOptOrderSalesBooksToClient(props.leadId, order.id)
    sendSalesBooksOpen.value = false
    message.success('Книги продаж отправлены клиенту')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось отправить книги продаж')
  } finally {
    sendingSalesBooksId.value = null
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

watch(needsPolling, () => {
  syncPolling()
})

// Only reset selection when switching deals — refresh/WS must keep the open tab.
watch(
  () => props.leadId,
  () => {
    selectedOrderId.value = null
    stopPolling()
    void loadOrders()
  },
  { immediate: true },
)

// Period may appear after mount (disabled→enabled) — reload orders.
watch(hasLead, (ok, wasOk) => {
  if (ok && !wasOk) void loadOrders()
})

watch(
  () => store.optOrdersRefreshNonce,
  () => {
    if (!hasLead.value) return
    void loadOrders({ silent: true })
  },
)

watch(
  () => props.initialOrderId,
  (id) => {
    if (id == null || !orders.value.some((row) => row.id === id)) return
    selectedOrderId.value = id
  },
)

watch(selectedOrderId, (id) => {
  void refreshReceiptsAvailability()
  const order = orders.value.find((row) => row.id === id)
  if (order) emit('select', order)
})

// Same selected id, but status became submitted (poll) — show docs buttons.
watch(
  () => selectedOrder.value?.status,
  (status, prev) => {
    if (status === 'submitted' && prev !== 'submitted') {
      void refreshReceiptsAvailability({ force: true })
    }
  },
)

onMounted(() => {
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  stopPolling()
  loadAbort?.abort()
})
</script>

<template>
  <section
    class="opt-orders"
    :class="{ 'opt-orders--wide': isWide, 'opt-orders--page': isPage }"
  >
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

    <NSpin class="opt-orders__spin" :show="loading && orders.length === 0">
      <p v-if="disabled && hasLead" class="opt-orders__hint">
        Сначала выберите период сделки ОПТ — без него заявку загрузить нельзя.
      </p>
      <NEmpty v-if="!orders.length" description="Заявок пока нет" />

      <template v-else>
        <div class="opt-orders__workspace">
        <div
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
              :class="statusPillClass(order)"
            >
              {{ statusLabel(order) }}
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
              :class="statusPillClass(selectedOrder)"
            >
              {{ statusLabel(selectedOrder) }}
            </NTag>
          </div>

          <p
            v-if="statusHint(selectedOrder) && (selectedOrder.payment_status === 'paid' || selectedOrder.payment_status === 'partial' || selectedOrder.receipts_sent_at || selectedOrder.status !== 'submitted')"
            class="opt-orders__hint"
          >
            {{ statusHint(selectedOrder) }}
          </p>

          <dl class="opt-orders__facts">
            <div>
              <dt>Объём</dt>
              <dd>{{ formatMoney(selectedOrder.total_volume) }} ₽</dd>
            </div>
            <div>
              <dt>НДС</dt>
              <dd>{{ selectedOrder.vat_rate_percent ?? optVatRateForPeriod(selectedOrder.period_code) }}%</dd>
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
                  class="opt-orders__period-select"
                  @update:value="(value) => onPeriodChange(value as string | null)"
                />
              </dd>
            </div>
            <div>
              <dt>К оплате</dt>
              <dd>
                {{ formatRubles(selectedOrder.commission_due) }} ₽
                <span
                  v-if="commissionAdjustment(selectedOrder) !== 0"
                  class="opt-orders__adjustment"
                >
                  (база {{ formatRubles(commissionBase(selectedOrder)) }} ₽,
                  {{ commissionAdjustment(selectedOrder) > 0 ? '+' : '' }}{{ formatRubles(commissionAdjustment(selectedOrder)) }} ₽)
                </span>
              </dd>
            </div>
            <div>
              <dt>Оплачено</dt>
              <dd>{{ formatRubles(selectedOrder.amount_paid) }} ₽</dd>
            </div>
            <div>
              <dt>Остаток</dt>
              <dd>{{ formatRubles(selectedOrder.amount_remaining) }} ₽</dd>
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

          <div
            v-if="!isBenik(selectedOrder) && volumeRows(selectedOrder).length"
            class="opt-orders__volume"
          >
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
                  <td>{{ formatRubles(row.commission) }} ₽</td>
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
                  <strong>{{ formatRubles(payment.amount) }} ₽</strong>
                  <span class="opt-orders__meta">
                    {{ new Date(payment.paid_at).toLocaleString('ru-RU') }} ·
                    {{ optPaymentTypeLabel(payment.payment_type) }} ·
                    {{ payment.created_by_name || `user #${payment.created_by}` }}
                  </span>
                  <OptPaymentDocuments
                    v-if="leadId != null"
                    compact
                    :lead-id="leadId"
                    :order-id="selectedOrder.id"
                    :payment="payment"
                  />
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
            :max-height="isPage ? undefined : isWide ? 280 : 200"
            :scroll-x="720"
            class="opt-orders__table"
          />

          <p v-if="selectedOrder.submission_error" class="opt-orders__error">
            {{ selectedOrder.submission_error }}
          </p>

          <div class="opt-orders__actions">
            <NButton
              v-if="canRecordPayment(selectedOrder)"
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
              v-if="selectedOrder.status === 'submitted' && receiptsAvailable"
              size="small"
              secondary
              :loading="downloadingReceiptsId === selectedOrder.id"
              @click="onDownloadReceipts(selectedOrder)"
            >
              Скачать квитанции
            </NButton>

            <NButton
              v-if="selectedOrder.status === 'submitted' && receiptsAvailable"
              size="small"
              type="primary"
              secondary
              @click="sendReceiptsOpen = true"
            >
              Отправить квитанции
            </NButton>

            <NButton
              v-if="selectedOrder.status === 'submitted' && salesBooksAvailable"
              size="small"
              secondary
              :loading="downloadingSalesBooksId === selectedOrder.id"
              @click="onDownloadSalesBooks(selectedOrder)"
            >
              Скачать книгу продаж
            </NButton>

            <NButton
              v-if="selectedOrder.status === 'submitted' && salesBooksAvailable"
              size="small"
              type="primary"
              secondary
              @click="sendSalesBooksOpen = true"
            >
              Отправить книгу продаж
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
        </div>
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
                  {{ formatRubles(item.old_commission_due) }} →
                  {{ formatRubles(item.new_commission_due) }} ₽
                  ({{ item.direction === 'decrease' ? 'скидка' : 'доначисление' }}
                  {{ formatRubles(Math.abs(item.delta)) }} ₽)
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
                  <strong>{{ formatRubles(payment.amount) }} ₽</strong>
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
                  <OptPaymentDocuments
                    v-if="leadId != null && selectedOrder"
                    :lead-id="leadId"
                    :order-id="selectedOrder.id"
                    :payment="payment"
                  />
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
            Подтвердите удаление заявки {{ orderLabel(deleteTarget) }}.
            Заявка скроется из списка (мягкое удаление); восстановить может администратор.
          </p>
          <p v-if="deleteTarget.payments.length" class="opt-orders__meta opt-orders__meta--warning">
            Оплаты по заявке тоже будут скрыты вместе с ней.
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
            Удалить заявку
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
          Базовая сумма: {{ formatRubles(commissionBase(selectedOrder)) }} ₽
        </p>
        <p v-if="commissionAdjustment(selectedOrder) !== 0" class="opt-orders__meta">
          Текущая корректировка:
          {{ commissionAdjustment(selectedOrder) > 0 ? '+' : '' }}{{ formatRubles(commissionAdjustment(selectedOrder)) }} ₽
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
              :min="1"
              :precision="0"
              :step="1"
              class="opt-orders__number"
            />
          </NFormItem>
        </NForm>
        <p v-if="commissionPreviewDue != null" class="opt-orders__preview-text">
          К оплате станет: <strong>{{ formatRubles(commissionPreviewDue) }} ₽</strong>
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
            :min="1"
            :precision="0"
            :step="1"
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

    <NModal
      v-model:show="sendReceiptsOpen"
      preset="card"
      title="Отправить квитанции клиенту"
      style="max-width: 420px"
    >
      <p>В чат будет отправлен ZIP с квитанциями и извещениями по лавкам этой заявки.</p>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="sendReceiptsOpen = false">Отмена</NButton>
          <NButton
            type="primary"
            :loading="selectedOrder != null && sendingReceiptsId === selectedOrder.id"
            :disabled="selectedOrder == null"
            @click="selectedOrder && onSendReceiptsToClient(selectedOrder)"
          >
            Отправить
          </NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal
      v-model:show="sendSalesBooksOpen"
      preset="card"
      title="Отправить книгу продаж клиенту"
      style="max-width: 420px"
    >
      <p>
        В чат будут отправлены короткие выписки книги продаж по парам
        продавец/покупатель этой заявки (без полных книг).
      </p>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="sendSalesBooksOpen = false">Отмена</NButton>
          <NButton
            type="primary"
            :loading="selectedOrder != null && sendingSalesBooksId === selectedOrder.id"
            :disabled="selectedOrder == null"
            @click="selectedOrder && onSendSalesBooksToClient(selectedOrder)"
          >
            Отправить
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </section>
</template>

<style scoped>
.opt-orders {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.opt-orders :deep(.n-spin-container),
.opt-orders :deep(.n-spin-content) {
  width: 100%;
  display: block;
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

.opt-orders__workspace {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  min-height: 0;
}

.opt-orders--page {
  flex: 1 1 auto;
  min-height: 0;
}

.opt-orders--page :deep(.opt-orders__spin.n-spin-container) {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
}

.opt-orders--page :deep(.opt-orders__spin .n-spin-content) {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
}

.opt-orders--page .opt-orders__workspace {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(200px, 260px) minmax(0, 1fr);
  align-items: stretch;
  gap: 12px;
}

.opt-orders--page .opt-orders__picker {
  display: flex;
  flex-direction: column;
  flex-wrap: nowrap;
  align-content: stretch;
  max-height: none;
  height: 100%;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 4px;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  background: var(--app-surface-elevated, transparent);
}

.opt-orders--page .opt-orders__tab {
  width: 100%;
  border-radius: 8px;
}

.opt-orders--page .opt-orders__header {
  flex-shrink: 0;
}

.opt-orders--page .opt-orders__detail {
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 16px 18px 18px;
  background: var(--app-surface);
  border-radius: 12px;
}

.opt-orders--page .opt-orders__actions {
  position: static;
  margin: 0;
  box-shadow: none;
  border-top: 1px solid var(--app-border);
  padding-top: 12px;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
}

.opt-orders--page .opt-orders__actions :deep(.n-button:last-child:nth-child(odd)) {
  grid-column: auto;
}

@media (max-width: 900px) {
  .opt-orders--page .opt-orders__workspace {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(96px, 30vh) minmax(0, 1fr);
  }

  .opt-orders--page .opt-orders__picker {
    flex-direction: row;
    flex-wrap: wrap;
    height: auto;
    max-height: 30vh;
  }

  .opt-orders--page .opt-orders__tab {
    width: auto;
  }

  .opt-orders--wide .opt-orders__facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
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

.opt-orders--wide .opt-orders__picker {
  max-height: 7.25rem;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: 2px;
}

.opt-orders__tab {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  width: auto;
  max-width: 100%;
  flex: 0 0 auto;
  min-width: 0;
  min-height: 28px;
  padding: 3px 8px;
  border: 1px solid var(--app-border);
  border-radius: 999px;
  background: var(--app-surface, transparent);
  cursor: pointer;
  font-size: 0.78rem;
  text-align: left;
  box-sizing: border-box;
}

.opt-orders__tab--active {
  border-color: var(--app-accent);
  background: color-mix(in srgb, var(--app-accent) 8%, transparent);
}

.opt-orders__tab-no {
  font-weight: 600;
  flex: 1 1 auto;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.opt-orders__tab :deep(.n-tag) {
  flex: 0 0 auto;
  max-width: none;
  justify-content: center;
}

.opt-orders__tab :deep(.n-tag .n-tag__content) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.opt-orders__detail {
  border: 1px solid var(--app-border);
  border-radius: 8px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
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
  min-height: 28px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
}

.opt-orders__period-select {
  width: 100%;
}

.opt-orders__facts dd :deep(.n-tag) {
  width: fit-content;
  max-width: 100%;
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
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  align-items: stretch;
}

.opt-orders__actions :deep(.n-button) {
  width: 100%;
  min-height: 32px;
  padding: 0 10px;
  justify-content: center;
}

.opt-orders__actions :deep(.n-button .n-button__content) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* одиночная кнопка в последнем ряду — на всю ширину */
.opt-orders__actions :deep(.n-button:last-child:nth-child(odd)) {
  grid-column: 1 / -1;
}

@media (max-width: 420px) {
  .opt-orders__actions {
    grid-template-columns: 1fr;
  }

  .opt-orders__actions :deep(.n-button:last-child:nth-child(odd)) {
    grid-column: auto;
  }
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

.opt-orders__payment-main :deep(.opt-pay-docs),
.opt-orders__payment-main :deep(.opt-pay-docs__empty) {
  margin-top: 4px;
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
