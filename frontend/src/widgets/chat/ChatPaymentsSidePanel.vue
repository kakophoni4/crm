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
  NSelect,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  NUpload,
  useMessage,
} from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { computed, h, onMounted, ref, watch } from 'vue'

import type { ChatDetail } from '@/entities/chat/types'
import { useChatsStore } from '@/features/chats/store'
import {
  addOptOrderPayment,
  downloadOptPaymentDocument,
  listOptOrders,
  listOptOrdersRegistry,
} from '@/features/leads/opt-api'
import type { OptOrder, OptOrderLine, OptOrderRegistryItem, OptPayment } from '@/features/leads/opt-types'
import {
  OPT_PAYMENT_RECIPIENT_OPTIONS,
  OPT_PAYMENT_TYPE_OPTIONS,
  optPaymentRecipientLabel,
  optPaymentStatusLabel,
  optPaymentTypeLabel,
} from '@/features/leads/opt-types'
import { uploadFile } from '@/features/chats/api'
import { AppError } from '@/shared/api/http'

defineProps<{
  chat: ChatDetail | null
}>()

const store = useChatsStore()
const message = useMessage()

const loading = ref(false)
const items = ref<OptOrderRegistryItem[]>([])
const total = ref(0)

const paymentOpen = ref(false)
const paymentTarget = ref<OptOrderRegistryItem | null>(null)
const savingPayment = ref(false)
const uploadingDocument = ref(false)
const paymentDocuments = ref<{ file_id: number; name: string }[]>([])
const paymentForm = ref<{
  amount: number | null
  paid_at: number
  payment_type: 'card' | 'crypto' | 'wire' | 'cash'
  recipient: 'orange' | 'beneficiary'
}>({
  amount: null,
  paid_at: Date.now(),
  payment_type: 'wire',
  recipient: 'orange',
})

const previewOpen = ref(false)
const previewTab = ref<'application' | 'commission' | 'payments'>('application')
const previewLoading = ref(false)
const previewOrder = ref<OptOrder | null>(null)
const historyDownloading = ref<string | null>(null)

const previewPayments = computed(() => {
  const order = previewOrder.value
  if (!order) return [] as OptPayment[]
  return [...order.payments].sort(
    (a, b) => new Date(b.paid_at).getTime() - new Date(a.paid_at).getTime(),
  )
})

const previewCommissionHistory = computed(() => previewOrder.value?.commission_history ?? [])

const lineColumns = computed<DataTableColumns<OptOrderLine>>(() => [
  {
    title: '№',
    key: 'line_no',
    width: 48,
  },
  {
    title: 'Поставщик',
    key: 'supplier',
    ellipsis: { tooltip: true },
    render: (row) => row.supplier.name || `ИНН ${row.supplier.inn}`,
  },
  {
    title: 'Документ',
    key: 'document_number',
    render: (row) =>
      row.document_number
        ? h('span', row.document_number)
        : h('span', { class: 'payments-side__muted' }, '—'),
  },
  {
    title: 'Сумма',
    key: 'amount',
    align: 'right',
    render: (row) => `${formatMoney(row.amount)} ₽`,
  },
])

function formatMoney(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

function paymentTagType(status: string): 'default' | 'success' | 'error' | 'warning' {
  if (status === 'paid') return 'success'
  if (status === 'partial') return 'warning'
  return 'error'
}

function clientLabel(row: OptOrderRegistryItem): string {
  return row.contact_name || row.buyer.name || `ИНН ${row.buyer.inn}`
}

async function loadItems(): Promise<void> {
  loading.value = true
  try {
    const data = await listOptOrdersRegistry({
      payment_status: 'unpaid,partial',
      open_only: true,
      limit: 100,
      offset: 0,
    })
    items.value = data.items
    total.value = data.total
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить оплаты')
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function openPayment(row: OptOrderRegistryItem): void {
  paymentTarget.value = row
  paymentForm.value = {
    amount: row.amount_remaining > 0 ? row.amount_remaining : null,
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
  const target = paymentTarget.value
  if (target == null) return
  if (paymentForm.value.amount == null || paymentForm.value.amount <= 0) {
    message.warning('Укажите сумму оплаты')
    return
  }
  savingPayment.value = true
  try {
    const fileIds = paymentDocuments.value.map((row) => row.file_id)
    const updated = await addOptOrderPayment(target.lead_id, target.id, {
      amount: paymentForm.value.amount,
      paid_at: new Date(paymentForm.value.paid_at).toISOString(),
      payment_type: paymentForm.value.payment_type,
      recipient: paymentForm.value.recipient,
      document_file_id: fileIds[0] ?? null,
      document_file_ids: fileIds,
    })
    paymentOpen.value = false
    paymentDocuments.value = []
    paymentTarget.value = null
    store.bumpOptOrdersRefresh()
    if (updated.payment_status === 'paid') {
      items.value = items.value.filter((row) => row.id !== updated.id)
      total.value = Math.max(0, total.value - 1)
    } else {
      items.value = items.value.map((row) =>
        row.id === updated.id
          ? {
              ...row,
              payment_status: updated.payment_status,
              commission_due: updated.commission_due,
              amount_paid: updated.amount_paid,
              amount_remaining: updated.amount_remaining,
              payments_count: updated.payments.length,
            }
          : row,
      )
    }
    message.success('Оплата записана')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось записать оплату')
  } finally {
    savingPayment.value = false
  }
}

async function openPreview(
  row: OptOrderRegistryItem,
  tab: 'application' | 'commission' | 'payments' = 'application',
): Promise<void> {
  previewTab.value = tab
  previewOpen.value = true
  previewLoading.value = true
  previewOrder.value = null
  try {
    const orders = await listOptOrders(row.lead_id)
    previewOrder.value = orders.find((order) => order.id === row.id) ?? null
    if (previewOrder.value == null) {
      message.warning('Заявка не найдена')
      previewOpen.value = false
    }
  } catch (err) {
    previewOpen.value = false
    message.error(err instanceof AppError ? err.message : 'Не удалось открыть заявку')
  } finally {
    previewLoading.value = false
  }
}

async function onDownloadHistoryDocument(
  order: OptOrder,
  paymentId: number,
  fileId?: number | null,
): Promise<void> {
  const key = `${paymentId}:${fileId ?? 'primary'}`
  historyDownloading.value = key
  try {
    const blob = await downloadOptPaymentDocument(order.lead_id, order.id, paymentId, fileId)
    const payment = order.payments.find((row) => row.id === paymentId)
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
  } finally {
    historyDownloading.value = null
  }
}

watch(
  () => store.optOrdersRefreshNonce,
  () => {
    void loadItems()
  },
)

onMounted(() => {
  void loadItems()
})
</script>

<template>
  <section class="payments-side">
    <header class="payments-side__header">
      <h2 class="payments-side__title">Оплаты</h2>
      <p class="payments-side__subtitle">
        Неоплаченные и частично оплаченные заявки
        <template v-if="total"> · {{ total }}</template>
      </p>
    </header>

    <div class="payments-side__scroll">
      <NSpin :show="loading">
        <NEmpty
          v-if="!loading && !items.length"
          description="Нет активных заявок к оплате"
        />
        <ul v-else class="payments-side__list">
          <li v-for="row in items" :key="row.id" class="payments-side__card">
            <div class="payments-side__card-top">
              <div>
                <strong>Сделка №{{ row.lead_id }} · заявка {{ row.order_no }}</strong>
                <p class="payments-side__client">{{ clientLabel(row) }}</p>
              </div>
              <NTag size="small" :type="paymentTagType(row.payment_status)" :bordered="true">
                {{ optPaymentStatusLabel(row.payment_status) }}
              </NTag>
            </div>
            <dl class="payments-side__facts">
              <div>
                <dt>К оплате</dt>
                <dd>{{ formatMoney(row.commission_due) }} ₽</dd>
              </div>
              <div>
                <dt>Оплачено</dt>
                <dd>{{ formatMoney(row.amount_paid) }} ₽</dd>
              </div>
              <div>
                <dt>Остаток</dt>
                <dd>{{ formatMoney(row.amount_remaining) }} ₽</dd>
              </div>
            </dl>
            <p v-if="row.payments_count" class="payments-side__history-hint">
              В истории {{ row.payments_count }}
              {{ row.payments_count === 1 ? 'оплата' : row.payments_count < 5 ? 'оплаты' : 'оплат' }}
            </p>
            <div class="payments-side__actions">
              <NButton size="small" type="primary" secondary @click="openPayment(row)">
                Внести оплату
              </NButton>
              <NButton size="small" quaternary @click="openPreview(row, 'payments')">
                История оплат
              </NButton>
              <NButton size="small" quaternary @click="openPreview(row)">
                Предпросмотр
              </NButton>
            </div>
          </li>
        </ul>
      </NSpin>
    </div>

    <NModal
      v-model:show="paymentOpen"
      preset="card"
      title="Записать оплату"
      style="max-width: 420px"
    >
      <p v-if="paymentTarget" class="payments-side__modal-meta">
        Сделка №{{ paymentTarget.lead_id }} · заявка {{ paymentTarget.order_no }} ·
        остаток {{ formatMoney(paymentTarget.amount_remaining) }} ₽
      </p>
      <NForm label-placement="top">
        <NFormItem label="Сумма оплаты">
          <NInputNumber
            v-model:value="paymentForm.amount"
            :min="0.01"
            :precision="2"
            style="width: 100%"
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
          <div class="payments-side__doc-upload">
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
            <ul v-if="paymentDocuments.length" class="payments-side__doc-list">
              <li v-for="doc in paymentDocuments" :key="doc.file_id">
                <span>{{ doc.name }}</span>
                <NButton
                  size="tiny"
                  quaternary
                  type="error"
                  @click="removePaymentDocument(doc.file_id)"
                >
                  Убрать
                </NButton>
              </li>
            </ul>
            <p v-else class="payments-side__muted">Можно прикрепить несколько файлов</p>
          </div>
        </NFormItem>
      </NForm>
      <template #footer>
        <div class="payments-side__modal-footer">
          <NButton @click="paymentOpen = false">Отмена</NButton>
          <NButton type="primary" :loading="savingPayment" @click="onSavePayment">
            Сохранить
          </NButton>
        </div>
      </template>
    </NModal>

    <NModal
      v-model:show="previewOpen"
      preset="card"
      :title="
        previewOrder
          ? `Предпросмотр · сделка №${previewOrder.lead_id} · заявка ${previewOrder.order_no}`
          : 'Предпросмотр'
      "
      style="max-width: 720px"
    >
      <NSpin :show="previewLoading">
        <template v-if="previewOrder">
          <p class="payments-side__modal-meta">
            {{ previewOrder.source_filename || previewOrder.crm_id }} ·
            к оплате {{ formatMoney(previewOrder.commission_due) }} ₽ ·
            остаток {{ formatMoney(previewOrder.amount_remaining) }} ₽
          </p>
          <NTabs v-model:value="previewTab" type="line" size="small" animated>
            <NTabPane name="application" tab="Заявка">
              <NDataTable
                size="small"
                :columns="lineColumns"
                :data="previewOrder.lines"
                :bordered="true"
                :pagination="false"
                :max-height="280"
              />
            </NTabPane>

            <NTabPane name="payments" tab="История оплаты">
              <ul v-if="previewPayments.length" class="payments-side__history-list">
                <li v-for="payment in previewPayments" :key="payment.id">
                  <div>
                    <strong>{{ formatMoney(payment.amount) }} ₽</strong>
                    <p class="payments-side__muted">
                      {{ new Date(payment.paid_at).toLocaleString('ru-RU') }} ·
                      {{ optPaymentTypeLabel(payment.payment_type) }} ·
                      {{ optPaymentRecipientLabel(payment.recipient) }}
                    </p>
                    <p class="payments-side__muted">
                      внёс: {{ payment.created_by_name || `user #${payment.created_by}` }}
                    </p>
                  </div>
                  <div class="payments-side__history-docs">
                    <template v-if="(payment.documents?.length || 0) > 0">
                      <NButton
                        v-for="doc in payment.documents"
                        :key="doc.file_id"
                        size="tiny"
                        quaternary
                        :loading="historyDownloading === `${payment.id}:${doc.file_id}`"
                        @click="onDownloadHistoryDocument(previewOrder, payment.id, doc.file_id)"
                      >
                        {{ doc.name || 'Документ' }}
                      </NButton>
                    </template>
                    <span v-else class="payments-side__muted">без документа</span>
                  </div>
                </li>
              </ul>
              <NEmpty v-else description="Оплат пока нет" />
            </NTabPane>

            <NTabPane name="commission" tab="История изменения суммы">
              <ul
                v-if="previewCommissionHistory.length"
                class="payments-side__history-list"
              >
                <li v-for="item in previewCommissionHistory" :key="item.id">
                  <div>
                    <strong>
                      {{ formatMoney(item.old_commission_due) }} →
                      {{ formatMoney(item.new_commission_due) }} ₽
                    </strong>
                    <p class="payments-side__muted">
                      {{ item.direction === 'decrease' ? 'скидка' : 'доначисление' }}
                      {{ formatMoney(Math.abs(item.delta)) }} ₽ ·
                      {{ item.changed_by_name || `user #${item.changed_by}` }} ·
                      {{ new Date(item.created_at).toLocaleString('ru-RU') }}
                    </p>
                  </div>
                </li>
              </ul>
              <NEmpty v-else description="Изменений суммы пока нет" />
            </NTabPane>
          </NTabs>
        </template>
      </NSpin>
    </NModal>
  </section>
</template>

<style scoped>
.payments-side {
  display: flex;
  flex-direction: column;
  flex: 1;
  height: 100%;
  min-height: 0;
  padding: 12px;
  overflow: hidden;
}

.payments-side__header {
  flex-shrink: 0;
  margin-bottom: 12px;
}

.payments-side__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
}

.payments-side__subtitle {
  margin: 4px 0 0;
  font-size: 0.8rem;
  color: var(--app-text-muted);
}

.payments-side__scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
  padding-bottom: 16px;
}

.payments-side__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.payments-side__card {
  padding: 12px 14px;
  border: 1px solid var(--app-border, var(--n-border-color));
  border-radius: 10px;
  background: var(--app-surface, transparent);
}

.payments-side__card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.payments-side__card-top strong {
  color: var(--app-text, inherit);
  font-size: 0.9rem;
}

.payments-side__client {
  margin: 4px 0 0;
  font-size: 0.85rem;
  color: var(--app-text-muted);
}

.payments-side__facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 10px 0;
  padding: 10px 0;
  border-top: 1px solid var(--app-border, var(--n-border-color));
  border-bottom: 1px solid var(--app-border, var(--n-border-color));
}

.payments-side__facts dt {
  font-size: 0.7rem;
  color: var(--app-text-muted);
}

.payments-side__facts dd {
  margin: 2px 0 0;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--app-text, inherit);
}

.payments-side__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.payments-side__history-hint {
  margin: 0 0 8px;
  font-size: 0.75rem;
  color: var(--app-text-muted);
}

.payments-side__history-list {
  list-style: none;
  margin: 0 0 8px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.payments-side__history-list li {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--app-border, var(--n-border-color));
}

.payments-side__history-list li:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.payments-side__history-docs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.payments-side__modal-meta,
.payments-side__muted {
  margin: 0 0 10px;
  font-size: 0.8rem;
  color: var(--app-text-muted);
}

.payments-side__section-title {
  margin: 14px 0 8px;
  font-size: 0.85rem;
  font-weight: 700;
}

.payments-side__doc-upload {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.payments-side__doc-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.payments-side__doc-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 0.8rem;
}

.payments-side__modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
