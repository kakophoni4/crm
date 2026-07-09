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
  downloadOptRegistry,
  listOptOrders,
  sendOptRegistryToClient,
  uploadOptApplication,
} from '@/features/leads/opt-api'
import { useChatsStore } from '@/features/chats/store'
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
const store = useChatsStore()
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
const commissionOpen = ref(false)
const deleteOpen = ref(false)
const deleteStep = ref<1 | 2>(1)
const deleteTarget = ref<OptOrder | null>(null)
const savingPayment = ref(false)
const savingCommission = ref(false)
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
  return order.payments.length === 0
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

function openCommissionModal(): void {
  commissionForm.value = {
    direction: 'decrease',
    amount: null,
  }
  commissionOpen.value = true
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
  () => [props.leadId, store.optOrdersRefreshNonce] as const,
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

            <NButton
              v-if="canAdjustCommission(selectedOrder)"
              size="small"
              quaternary
              @click="openCommissionModal()"
            >
              Изменить к оплате
            </NButton>

            <NButton
              v-if="canDeleteOrder(selectedOrder)"
              size="small"
              type="error"
              quaternary
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
          <p v-if="deleteTarget.status === 'submitted'" class="opt-orders__meta opt-orders__meta--warning">
            Заявка уже отправлена в 1С. Удаление затронет только CRM — запись в 1С останется.
          </p>
        </template>
        <template v-else>
          <p class="opt-orders__preview-text">
            Это действие необратимо. Заявка и все связанные строки будут удалены без восстановления.
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
  gap: 6px;
  font-size: 0.78rem;
}

.opt-orders__payments-list li {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
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
