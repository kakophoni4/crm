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
  NPopconfirm,
  NSelect,
  NSpin,
  NTag,
  NUpload,
  useMessage,
} from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { computed, h, onUnmounted, ref, watch } from 'vue'

import {
  addOptOrderPayment,
  deleteOptOrder,
  downloadOptRegistry,
  listOptOrders,
  sendOptRegistryToClient,
  uploadOptApplication,
} from '@/features/leads/opt-api'
import type { OptOrder, OptOrderLine } from '@/features/leads/opt-types'
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
}>()

const emit = defineEmits<{
  paymentsChanged: []
}>()

const message = useMessage()
const loading = ref(false)
const uploading = ref(false)
const deletingId = ref<number | null>(null)
const downloadingId = ref<number | null>(null)
const sendingId = ref<number | null>(null)
const orders = ref<OptOrder[]>([])
const selectedOrderId = ref<number | null>(null)
const previewOpen = ref(false)
const sendPreviewOpen = ref(false)
const paymentOpen = ref(false)
const savingPayment = ref(false)
const paymentForm = ref({
  amount: null as number | null,
  paid_at: Date.now(),
  payment_type: 'wire' as 'card' | 'crypto' | 'wire' | 'cash',
  recipient: 'orange' as 'orange' | 'beneficiary',
})
let pollTimer: ReturnType<typeof setInterval> | null = null

const hasLead = computed(() => props.leadId != null && !props.disabled)

const selectedOrder = computed(
  () => orders.value.find((row) => row.id === selectedOrderId.value) ?? null,
)

const needsPolling = computed(() =>
  orders.value.some((row) => row.status === 'queued' || row.status === 'submitting'),
)

const hasPendingSubmission = computed(() =>
  orders.value.some(
    (row) => row.status === 'failed' || row.status === 'queued' || row.status === 'submitting',
  ),
)

function canDeleteOrder(order: OptOrder): boolean {
  return order.status !== 'submitted' && order.payments.length === 0
}

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
])

function paymentTagType(status: string): 'default' | 'success' | 'error' | 'warning' {
  if (status === 'paid') return 'success'
  if (status === 'partial') return 'warning'
  return 'error'
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
  paymentOpen.value = true
}

async function onSavePayment(): Promise<void> {
  if (!selectedOrder.value || props.leadId == null) return
  if (paymentForm.value.amount == null || paymentForm.value.amount <= 0) {
    message.warning('Укажите сумму оплаты')
    return
  }
  savingPayment.value = true
  try {
    const updated = await addOptOrderPayment(props.leadId, selectedOrder.value.id, {
      amount: paymentForm.value.amount,
      paid_at: new Date(paymentForm.value.paid_at).toISOString(),
      payment_type: paymentForm.value.payment_type,
      recipient: paymentForm.value.recipient,
    })
    orders.value = orders.value
      .map((row) => (row.id === updated.id ? updated : row))
      .sort((a, b) => a.order_no - b.order_no)
    paymentOpen.value = false
    emit('paymentsChanged')
    message.success('Оплата записана')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось записать оплату')
  } finally {
    savingPayment.value = false
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
  if (!options?.silent) loading.value = true
  try {
    const items = await listOptOrders(props.leadId)
    orders.value = [...items].sort((a, b) => a.order_no - b.order_no)
    selectedOrderId.value = pickSelectedOrder(orders.value, selectedOrderId.value)
  } catch (err) {
    if (!options?.silent) {
      message.error(err instanceof AppError ? err.message : 'Не удалось загрузить заявки')
    }
    orders.value = []
    selectedOrderId.value = null
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
    const created = await uploadOptApplication(props.leadId, raw)
    orders.value = [...orders.value.filter((row) => row.id !== created.id), created].sort(
      (a, b) => a.order_no - b.order_no,
    )
    selectedOrderId.value = created.id
    startPolling()
    message.success(`Заявка ${created.order_no} загружена — реестр формируется`)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить заявку')
  } finally {
    uploading.value = false
  }
}

async function onDelete(order: OptOrder): Promise<void> {
  if (props.leadId == null || !canDeleteOrder(order)) return
  deletingId.value = order.id
  try {
    await deleteOptOrder(props.leadId, order.id)
    orders.value = orders.value.filter((row) => row.id !== order.id)
    selectedOrderId.value = pickSelectedOrder(orders.value, null)
    if (!needsPolling.value) stopPolling()
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
  () => props.leadId,
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
  <section class="opt-orders">
    <header class="opt-orders__header">
      <div>
        <h3 class="opt-orders__title">
          <template v-if="leadId">Сделка №{{ leadId }} · заявки ОПТ</template>
          <template v-else>Заявки ОПТ</template>
        </h3>
        <p v-if="orders.length" class="opt-orders__count">{{ orders.length }} шт.</p>
      </div>
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
    </header>

    <NSpin :show="loading">
      <NEmpty v-if="!orders.length" description="Заявок пока нет" />

      <template v-else>
        <div class="opt-orders__picker" role="tablist" aria-label="Заявки сделки">
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
            <NTag size="tiny" :type="statusTagType(order.status)" :bordered="false">
              {{ statusLabel(order.status) }}
            </NTag>
          </button>
        </div>

        <article v-if="selectedOrder" class="opt-orders__detail">
          <div class="opt-orders__detail-head">
            <div>
              <strong>Сделка №{{ selectedOrder.lead_id }} · {{ orderLabel(selectedOrder) }}</strong>
              <span class="opt-orders__meta">
                {{ selectedOrder.source_filename || selectedOrder.crm_id }}
              </span>
            </div>
            <NTag size="small" :type="statusTagType(selectedOrder.status)" :bordered="false">
              {{ statusLabel(selectedOrder.status) }}
            </NTag>
          </div>

          <p v-if="statusHint(selectedOrder.status)" class="opt-orders__hint">
            {{ statusHint(selectedOrder.status) }}
          </p>

          <dl class="opt-orders__facts">
            <div>
              <dt>Объём</dt>
              <dd>{{ formatMoney(selectedOrder.total_volume) }} ₽</dd>
            </div>
            <div>
              <dt>К оплате</dt>
              <dd>{{ formatMoney(selectedOrder.commission_due) }} ₽</dd>
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
                <NTag size="small" :type="paymentTagType(selectedOrder.payment_status)" :bordered="false">
                  {{ optPaymentStatusLabel(selectedOrder.payment_status) }}
                </NTag>
              </dd>
            </div>
            <div>
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

          <div v-if="selectedOrder.payments.length" class="opt-orders__payments">
            <h4 class="opt-orders__subheading">Оплаты</h4>
            <ul class="opt-orders__payments-list">
              <li v-for="payment in selectedOrder.payments" :key="payment.id">
                <span>{{ formatMoney(payment.amount) }} ₽</span>
                <span>{{ new Date(payment.paid_at).toLocaleString('ru-RU') }}</span>
                <span>{{ optPaymentTypeLabel(payment.payment_type) }}</span>
                <span>{{ optPaymentRecipientLabel(payment.recipient) }}</span>
              </li>
            </ul>
          </div>

          <NDataTable
            size="small"
            :columns="lineColumns"
            :data="selectedOrder.lines"
            :bordered="false"
            :pagination="false"
            :max-height="220"
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
              @click="openPaymentModal(selectedOrder)"
            >
              Записать оплату
            </NButton>

            <NButton size="small" quaternary @click="previewOpen = true">Предпросмотр</NButton>

            <NButton
              v-if="selectedOrder.status === 'submitted'"
              size="small"
              :loading="downloadingId === selectedOrder.id"
              @click="onDownload(selectedOrder)"
            >
              Скачать реестр
            </NButton>

            <NButton
              v-if="selectedOrder.status === 'submitted'"
              size="small"
              type="primary"
              @click="sendPreviewOpen = true"
            >
              Отправить клиенту
            </NButton>

            <NPopconfirm
              v-if="canDeleteOrder(selectedOrder)"
              positive-text="Удалить"
              negative-text="Отмена"
              @positive-click="() => { if (selectedOrder) void onDelete(selectedOrder) }"
            >
              <template #trigger>
                <NButton
                  size="small"
                  type="error"
                  quaternary
                  :loading="deletingId === selectedOrder.id"
                >
                  Удалить заявку
                </NButton>
              </template>
              Удалить заявку {{ orderLabel(selectedOrder) }}? Это действие нельзя отменить.
            </NPopconfirm>
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
        <p class="opt-orders__preview-text">{{ clientMessagePreview(selectedOrder) }}</p>
        <NDataTable
          size="small"
          :columns="lineColumns"
          :data="selectedOrder.lines"
          :bordered="true"
          :pagination="false"
          :max-height="360"
        />
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

.opt-orders__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
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
  border-color: var(--app-accent, #2080f0);
  background: color-mix(in srgb, var(--app-accent, #2080f0) 8%, transparent);
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
}

.opt-orders__doc-no {
  color: var(--app-accent, #2080f0);
  font-weight: 600;
}

.opt-orders__error {
  margin: 0;
  color: #d03050;
  font-size: 0.8rem;
}

.opt-orders__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.opt-orders__preview-text {
  margin: 0 0 12px;
  font-size: 0.85rem;
}

.opt-orders__quote {
  margin: 0 0 12px;
  padding: 10px 12px;
  border-left: 3px solid var(--app-accent, #2080f0);
  background: var(--app-surface-2, rgba(0, 0, 0, 0.03));
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
  gap: 6px;
  font-size: 0.78rem;
}

.opt-orders__payments-list li {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.opt-orders__number {
  width: 100%;
}
</style>
