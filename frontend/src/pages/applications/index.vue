<script setup lang="ts">
import type { DataTableColumns, DataTableRowKey } from 'naive-ui'
import {
  NButton,
  NDataTable,
  NEmpty,
  NModal,
  NPagination,
  NSelect,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  useMessage,
} from 'naive-ui'
import { ClipboardList, MessageSquare } from 'lucide-vue-next'
import { computed, h, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { listDepartments, type Department } from '@/features/admin/api'
import { downloadOptPaymentDocument, listOptOrdersRegistry, listOptPaymentsLedger } from '@/features/leads/opt-api'
import type { OptOrderRegistryItem, OptPaymentLedgerItem } from '@/features/leads/opt-types'
import {
  OPT_PAYMENT_TYPE_OPTIONS,
  optPaymentRecipientLabel,
  optPaymentStatusLabel,
  optPaymentTypeLabel,
} from '@/features/leads/opt-types'
import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'
import AppCard from '@/shared/ui/AppCard.vue'
import OptOrdersPanel from '@/widgets/chat/OptOrdersPanel.vue'

type TabName = 'orders' | 'payments'

const message = useMessage()
const router = useRouter()
const auth = useAuthStore()

const activeTab = ref<TabName>('orders')
const loading = ref(false)
const items = ref<OptOrderRegistryItem[]>([])
const paymentItems = ref<OptPaymentLedgerItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 30
const paymentStatusFilter = ref<string | null>(null)
const paymentTypeFilter = ref<string | null>(null)
const selectedDeptKey = ref<string>('all')
const departments = ref<Department[]>([])

const detailOpen = ref(false)
const selected = ref<OptOrderRegistryItem | null>(null)

const paymentStatusOptions = [
  { label: 'Все', value: 'all' },
  { label: 'Не оплаченные', value: 'unpaid' },
  { label: 'Частично', value: 'partial' },
  { label: 'Оплаченные', value: 'paid' },
]

const paymentTypeOptions = OPT_PAYMENT_TYPE_OPTIONS.map((row) => ({
  label: row.label,
  value: row.value,
}))

function formatMoney(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('ru-RU')
  } catch {
    return iso
  }
}

function paymentTagType(status: string): 'default' | 'success' | 'error' | 'warning' {
  if (status === 'paid') return 'success'
  if (status === 'partial') return 'warning'
  return 'error'
}

function deptFilterId(): number | undefined {
  if (selectedDeptKey.value === 'all' || selectedDeptKey.value === 'none') return undefined
  const n = Number(selectedDeptKey.value)
  return Number.isFinite(n) ? n : undefined
}

const departmentOptions = computed(() => [
  { label: 'Все отделы', value: 'all' },
  ...departments.value.map((row) => ({
    value: String(row.id),
    label: row.name,
  })),
])

const groupedByDepartment = computed(() => {
  const groups = new Map<string, { label: string; rows: OptOrderRegistryItem[] }>()
  for (const row of items.value) {
    const key = row.department_id != null ? String(row.department_id) : 'none'
    const label =
      row.department_name ||
      (row.department_id != null ? `Отдел #${row.department_id}` : 'Без отдела')
    if (!groups.has(key)) groups.set(key, { label, rows: [] })
    groups.get(key)!.rows.push(row)
  }
  return [...groups.values()]
})

const columns = computed<DataTableColumns<OptOrderRegistryItem>>(() => [
  {
    title: 'Заявка',
    key: 'order',
    render: (row) => `Сделка №${row.lead_id} · №${row.order_no}`,
  },
  {
    title: 'Клиент',
    key: 'contact',
    ellipsis: { tooltip: true },
    render: (row) => row.contact_name || row.buyer.name || `ИНН ${row.buyer.inn}`,
  },
  {
    title: 'Группа',
    key: 'group',
    render: (row) => row.group_name || `Группа #${row.group_id}`,
  },
  {
    title: 'К оплате',
    key: 'commission_due',
    align: 'right',
    render: (row) => `${formatMoney(row.commission_due)} ₽`,
  },
  {
    title: 'Оплачено',
    key: 'amount_paid',
    align: 'right',
    render: (row) => `${formatMoney(row.amount_paid)} ₽`,
  },
  {
    title: 'Оплата',
    key: 'payment_status',
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: paymentTagType(row.payment_status), bordered: false },
        { default: () => optPaymentStatusLabel(row.payment_status) },
      ),
  },
])

const paymentColumns = computed<DataTableColumns<OptPaymentLedgerItem>>(() => [
  {
    title: 'Дата',
    key: 'paid_at',
    width: 160,
    render: (row) => formatDateTime(row.paid_at),
  },
  {
    title: 'Сумма',
    key: 'amount',
    align: 'right',
    width: 120,
    render: (row) => `${formatMoney(row.amount)} ₽`,
  },
  {
    title: 'Тип',
    key: 'payment_type',
    width: 110,
    render: (row) => optPaymentTypeLabel(row.payment_type),
  },
  {
    title: 'Куда',
    key: 'recipient',
    width: 120,
    render: (row) => optPaymentRecipientLabel(row.recipient),
  },
  {
    title: 'Заявка',
    key: 'order',
    render: (row) => `Сделка №${row.lead_id} · №${row.order_no}`,
  },
  {
    title: 'Клиент',
    key: 'contact',
    ellipsis: { tooltip: true },
    render: (row) => row.contact_name || row.buyer.name || `ИНН ${row.buyer.inn}`,
  },
  {
    title: 'Статус заявки',
    key: 'order_payment_status',
    width: 120,
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: paymentTagType(row.order_payment_status), bordered: false },
        { default: () => optPaymentStatusLabel(row.order_payment_status) },
      ),
  },
  {
    title: 'Кто внёс',
    key: 'created_by',
    ellipsis: { tooltip: true },
    render: (row) => row.created_by_name || `user #${row.created_by}`,
  },
  {
    title: 'Документ',
    key: 'doc',
    width: 110,
    render: (row) => {
      if (!row.documents_count) return '—'
      return h(
        NButton,
        {
          size: 'tiny',
          quaternary: true,
          type: 'primary',
          onClick: (e: MouseEvent) => {
            e.stopPropagation()
            void downloadPaymentDoc(row)
          },
        },
        { default: () => (row.documents_count > 1 ? `Файлы (${row.documents_count})` : 'Скачать') },
      )
    },
  },
])

function rowKey(row: OptOrderRegistryItem): DataTableRowKey {
  return row.id
}

function paymentRowKey(row: OptPaymentLedgerItem): DataTableRowKey {
  return row.id
}

function rowProps(row: OptOrderRegistryItem) {
  return {
    style: 'cursor: pointer',
    onClick: () => openDetail(row),
  }
}

function paymentRowProps(row: OptPaymentLedgerItem) {
  return {
    style: 'cursor: pointer',
    onClick: () => openDetailFromPayment(row),
  }
}

function openDetail(row: OptOrderRegistryItem): void {
  selected.value = row
  detailOpen.value = true
}

function openDetailFromPayment(row: OptPaymentLedgerItem): void {
  selected.value = {
    id: row.order_id,
    lead_id: row.lead_id,
    order_no: row.order_no,
    chat_id: row.chat_id,
    contact_id: row.contact_id,
    contact_name: row.contact_name,
    group_id: row.group_id,
    group_name: row.group_name,
    department_id: row.department_id,
    department_name: row.department_name,
    status: '',
    payment_status: row.order_payment_status,
    total_volume: 0,
    commission_due: row.order_commission_due,
    amount_paid: row.order_amount_paid,
    amount_remaining: Math.max(0, row.order_commission_due - row.order_amount_paid),
    buyer: row.buyer,
    source_filename: null,
    created_at: row.created_at,
    lines_count: 0,
    payments_count: 0,
  }
  detailOpen.value = true
}

async function downloadPaymentDoc(row: OptPaymentLedgerItem): Promise<void> {
  try {
    const blob = await downloadOptPaymentDocument(
      row.lead_id,
      row.order_id,
      row.id,
      row.document_file_id,
    )
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `payment-${row.id}`
    a.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать документ')
  }
}

function resolvedPaymentStatus(): string | undefined {
  const value = paymentStatusFilter.value
  if (value == null || value === 'all') return undefined
  return value
}

async function loadOrders(): Promise<void> {
  loading.value = true
  try {
    const data = await listOptOrdersRegistry({
      payment_status: resolvedPaymentStatus(),
      department_id: deptFilterId(),
      offset: (page.value - 1) * pageSize,
      limit: pageSize,
    })
    items.value = data.items
    total.value = data.total
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить заявки')
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadPayments(): Promise<void> {
  loading.value = true
  try {
    const data = await listOptPaymentsLedger({
      payment_type: paymentTypeFilter.value ?? undefined,
      payment_status: resolvedPaymentStatus(),
      department_id: deptFilterId(),
      offset: (page.value - 1) * pageSize,
      limit: pageSize,
    })
    paymentItems.value = data.items
    total.value = data.total
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить оплаты')
    paymentItems.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function load(): Promise<void> {
  if (activeTab.value === 'payments') {
    await loadPayments()
  } else {
    await loadOrders()
  }
}

function onDetailPaymentsChanged(): void {
  void load()
}

function goToChat(): void {
  const chatId = selected.value?.chat_id
  if (chatId == null) {
    message.warning('У заявки нет связанного чата')
    return
  }
  void router.push({ name: 'chats', query: { chatId: String(chatId) } })
}

function onTabChange(name: string | number): void {
  activeTab.value = name === 'payments' ? 'payments' : 'orders'
  page.value = 1
  void load()
}

watch([page, paymentStatusFilter, paymentTypeFilter, selectedDeptKey], () => {
  void load()
})

onMounted(() => {
  void load()
  if (auth.isAdmin || auth.isSenior || auth.isGroupSenior) {
    void listDepartments()
      .then((rows) => {
        departments.value = rows
      })
      .catch(() => {
        departments.value = []
      })
  }
})
</script>

<template>
  <div class="applications-page">
    <header class="applications-page__header">
      <div>
        <h1 class="applications-page__title">
          <ClipboardList :size="22" />
          Заявки ОПТ
        </h1>
        <p class="applications-page__subtitle">
          <template v-if="auth.isAdmin">Все данные по всем отделам</template>
          <template v-else-if="auth.isSenior">Данные вашего отдела</template>
          <template v-else-if="auth.isGroupSenior">Данные ваших групп</template>
          <template v-else>Данные вашей группы</template>
        </p>
      </div>
      <div class="applications-page__filters">
        <NSelect
          v-if="auth.isAdmin || auth.isSenior"
          v-model:value="selectedDeptKey"
          :options="departmentOptions"
          style="width: 220px"
          size="small"
        />
        <NSelect
          v-model:value="paymentStatusFilter"
          :options="paymentStatusOptions"
          placeholder="Статус оплаты"
          style="width: 200px"
          size="small"
          clearable
        />
        <NSelect
          v-if="activeTab === 'payments'"
          v-model:value="paymentTypeFilter"
          :options="paymentTypeOptions"
          placeholder="Все типы оплаты"
          style="width: 180px"
          size="small"
          clearable
        />
      </div>
    </header>

    <NTabs :value="activeTab" type="line" @update:value="onTabChange">
      <NTabPane name="orders" tab="Заявки" />
      <NTabPane name="payments" tab="Все оплаты" />
    </NTabs>

    <NSpin :show="loading">
      <template v-if="activeTab === 'orders'">
        <NEmpty v-if="!items.length && !loading" description="Заявок пока нет" />
        <div v-else class="applications-page__groups">
          <AppCard
            v-for="group in groupedByDepartment"
            :key="group.label"
            class="applications-page__card"
          >
            <h2 class="applications-page__group-title">{{ group.label }}</h2>
            <NDataTable
              size="small"
              :columns="columns"
              :data="group.rows"
              :row-key="rowKey"
              :row-props="rowProps"
              :bordered="false"
              :pagination="false"
            />
          </AppCard>
        </div>
      </template>

      <template v-else>
        <NEmpty v-if="!paymentItems.length && !loading" description="Оплат пока нет" />
        <AppCard v-else class="applications-page__card">
          <NDataTable
            size="small"
            :columns="paymentColumns"
            :data="paymentItems"
            :row-key="paymentRowKey"
            :row-props="paymentRowProps"
            :bordered="false"
            :pagination="false"
          />
        </AppCard>
      </template>
    </NSpin>

    <div v-if="total > pageSize" class="applications-page__pager">
      <NPagination v-model:page="page" :page-size="pageSize" :item-count="total" />
    </div>

    <NModal
      v-model:show="detailOpen"
      preset="card"
      :title="selected ? `Сделка №${selected.lead_id} · заявка №${selected.order_no}` : 'Заявка'"
      class="applications-page__modal"
      :style="{ width: 'min(1120px, 96vw)' }"
      :segmented="{ content: true, footer: 'soft' }"
    >
      <template v-if="selected">
        <dl class="applications-page__facts">
          <div>
            <dt>Клиент</dt>
            <dd>{{ selected.contact_name || '—' }}</dd>
          </div>
          <div>
            <dt>Покупатель</dt>
            <dd>{{ selected.buyer.name || `ИНН ${selected.buyer.inn}` }}</dd>
          </div>
          <div>
            <dt>Отдел / группа</dt>
            <dd>
              {{ selected.department_name || '—' }} /
              {{ selected.group_name || `Группа #${selected.group_id}` }}
            </dd>
          </div>
        </dl>

        <div class="applications-page__panel">
          <OptOrdersPanel
            layout="wide"
            :lead-id="selected.lead_id"
            :initial-order-id="selected.id"
            @payments-changed="onDetailPaymentsChanged"
          />
        </div>
      </template>

      <template #footer>
        <div class="applications-page__footer">
          <NButton @click="detailOpen = false">Закрыть</NButton>
          <NButton type="primary" :disabled="!selected?.chat_id" @click="goToChat">
            <template #icon><MessageSquare :size="16" /></template>
            Перейти в чат
          </NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.applications-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 20px 24px;
  min-height: 0;
}

.applications-page__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.applications-page__title {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
}

.applications-page__subtitle {
  margin: 4px 0 0;
  font-size: 0.85rem;
  color: var(--app-text-muted);
}

.applications-page__filters {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.applications-page__groups {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.applications-page__group-title {
  margin: 0 0 10px;
  font-size: 0.95rem;
  font-weight: 700;
}

.applications-page__pager {
  display: flex;
  justify-content: flex-end;
}

.applications-page__facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px 20px;
  margin: 0 0 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--n-border-color);
}

.applications-page__facts dt {
  font-size: 0.75rem;
  color: var(--app-text-muted);
}

.applications-page__facts dd {
  margin: 4px 0 0;
  font-weight: 600;
  line-height: 1.35;
  word-break: break-word;
}

.applications-page__panel {
  min-height: 0;
}

.applications-page__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 800px) {
  .applications-page__facts {
    grid-template-columns: 1fr;
  }
}

:deep(.n-data-table-tr) {
  transition: background 0.12s ease;
}

:deep(.n-data-table-tr:hover) {
  background: color-mix(in srgb, var(--app-accent, #3b82f6) 8%, transparent);
}
</style>

<style>
.applications-page__modal.n-card {
  max-height: calc(100vh - 40px);
}

.applications-page__modal.n-card > .n-card__content {
  max-height: calc(100vh - 180px);
  overflow: auto;
}
</style>
