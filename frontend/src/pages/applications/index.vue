<script setup lang="ts">
import type { DataTableColumns, DataTableRowKey, SelectOption } from 'naive-ui'
import {
  NButton,
  NDataTable,
  NEmpty,
  NInput,
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
import { watchDebounced } from '@vueuse/core'
import { computed, h, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { listGroups, type Group } from '@/features/admin/api'
import {
  listOptOrderManagers,
  listOptOrdersRegistry,
  listOptPaymentRegister,
  patchOptOrderPeriod,
  syncOptOrdersWith1c,
} from '@/features/leads/opt-api'
import type {
  OptOrderRegistryItem,
  OptPayment,
  OptPaymentLedgerItem,
  OptPaymentRegisterItem,
  OptRegistryManagerItem,
  OptSync1cResponse,
} from '@/features/leads/opt-types'
import {
  optPaymentRecipientLabel,
  optPaymentStatusLabel,
  optPaymentTypeLabel,
} from '@/features/leads/opt-types'
import { formatOptPeriodLabel, OPT_PERIOD_OPTIONS } from '@/features/leads/order-fields'
import { VIRTUAL_DATA_TABLE_MIN_ROW_HEIGHT } from '@/shared/ui/virtual-data-table'
import { AppError, http } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'
import OptPaymentDocuments from '@/widgets/chat/OptPaymentDocuments.vue'

type TabName = 'orders' | 'payments' | 'benik'

const message = useMessage()
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const activeTab = ref<TabName>('orders')
const loading = ref(false)
const items = ref<OptOrderRegistryItem[]>([])
const paymentItems = ref<OptPaymentLedgerItem[]>([])
const paymentRegisterItems = ref<OptPaymentRegisterItem[]>([])
const paymentRegisterDetailOpen = ref(false)
const selectedPaymentRegister = ref<OptPaymentRegisterItem | null>(null)
const total = ref(0)
const totalVolumeSum = ref(0)
const commissionDueSum = ref(0)
const amountPaidSum = ref(0)

const paymentRegisterTotals = computed(() =>
  paymentRegisterItems.value.reduce(
    (totals, row) => ({
      volume: totals.volume + Number(row.volume || 0),
      due: totals.due + Number(row.due_amount || 0),
      paid: totals.paid + Number(row.paid_amount || 0),
      remaining: totals.remaining + Number(row.remaining_amount || 0),
    }),
    { volume: 0, due: 0, paid: 0, remaining: 0 },
  ),
)

const selectedPaymentRegisterShops = computed(() => {
  const lines = selectedPaymentRegister.value?.lines ?? []
  const grouped = new Map<string, { name: string; inn: string; category: string; lines: number; volume: number; due: number; beneficiary: number; actual: number; planned: number }>()
  for (const line of lines) {
    const key = line.supplier_inn || String(line.id)
    const current = grouped.get(key) ?? {
      name: line.supplier_name || `ИНН ${line.supplier_inn}`,
      inn: line.supplier_inn,
      category: line.category_code || 'категория не указана',
      lines: 0, volume: 0, due: 0, beneficiary: 0, actual: 0, planned: 0,
    }
    current.lines += 1
    current.volume += Number(line.volume || 0)
    current.due += Number(line.due_amount || 0)
    current.beneficiary += Number(line.beneficiary_amount || 0)
    current.actual += Number(line.actual_margin || 0)
    current.planned += Number(line.planned_margin || 0)
    grouped.set(key, current)
  }
  return [...grouped.values()]
})

const totalsScopeHint = computed(() => {
  if (auth.isAdmin) return 'по всем отделам'
  if (auth.isSenior) return 'по вашему отделу'
  if (auth.isGroupSenior) return 'по вашим группам'
  return 'по вашим заявкам'
})
const page = ref(1)
const pageSize = 30
const paymentStatusFilter = ref<string | null>(null)
const periodFilter = ref<string | null>(null)
const selectedGroupKey = ref<string>('all')
const managerFilter = ref<number | null>(null)
const buyerSearch = ref('')
const buyerSearchApplied = ref('')
const groups = ref<Group[]>([])
const managers = ref<OptRegistryManagerItem[]>([])
const periodOptions = OPT_PERIOD_OPTIONS
const savingPeriodOrderId = ref<number | null>(null)
const editingPeriodOrderId = ref<number | null>(null)
const syncing1c = ref(false)
const syncReportOpen = ref(false)
const syncReport = ref<OptSync1cResponse | null>(null)
const blacklistOpen = ref(false)
const blacklistKind = ref<'telegram_username' | 'buyer_inn'>('telegram_username')
const blacklistValue = ref('')
const blacklistReason = ref('')
const blacklistItems = ref<Array<{ id: number; kind: 'telegram_username' | 'buyer_inn'; value: string; reason: string }>>([])
const blacklistLoading = ref(false)
const blacklistSaving = ref(false)

const canFilterGroup = computed(
  () => auth.isAdmin || auth.isSenior || auth.isGroupSenior,
)
const canFilterManager = computed(() => auth.isAdmin || auth.isSenior)
const canSync1c = computed(() => auth.isAdmin)

const paymentDetailOpen = ref(false)
const selectedPayment = ref<OptPaymentLedgerItem | null>(null)
const paymentHistoryLoading = ref(false)
const paymentHistory = ref<OptPayment[]>([])
const selectedPaymentDocs = computed(() => {
  const selected = selectedPayment.value
  if (!selected) return null
  const fromHistory = paymentHistory.value.find((item) => item.id === selected.id)
  if (fromHistory) {
    return {
      id: fromHistory.id,
      documents: fromHistory.documents,
      document_file_id: fromHistory.document_file_id,
      document_name: fromHistory.document_name,
    }
  }
  return {
    id: selected.id,
    documents: undefined,
    document_file_id: selected.document_file_id,
    document_name: selected.documents_count > 0 ? 'Подтверждение оплаты' : null,
  }
})

const paymentStatusOptions = computed(() => {
  if (activeTab.value === 'payments') {
    return [
      { label: 'Все проведённые', value: 'all' },
      { label: 'Частично', value: 'partial' },
      { label: 'Оплаченные', value: 'paid' },
    ]
  }
  return [
    { label: 'Все', value: 'all' },
    { label: 'Не оплаченные', value: 'unpaid' },
    { label: 'Частично', value: 'partial' },
    { label: 'Оплаченные', value: 'paid' },
  ]
})

function registryKind(): 'standard' | 'benik' {
  return activeTab.value === 'benik' ? 'benik' : 'standard'
}

const isOrdersLikeTab = computed(() => activeTab.value === 'orders' || activeTab.value === 'benik')

const managerOptions = computed<SelectOption[]>(() =>
  managers.value.map((row) => ({
    value: row.id,
    label: row.full_name || `user #${row.id}`,
  })),
)

async function onOrderPeriodChange(
  row: OptOrderRegistryItem,
  value: string | null,
): Promise<void> {
  if (!value || value === row.period_code) return
  savingPeriodOrderId.value = row.id
  try {
    const updated = await patchOptOrderPeriod(row.id, value)
    row.period_code = updated.period_code
    message.success('Период сохранён')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить период')
  } finally {
    savingPeriodOrderId.value = null
    editingPeriodOrderId.value = null
  }
}

function renderPeriodCell(row: OptOrderRegistryItem) {
  const isEditing =
    editingPeriodOrderId.value === row.id || savingPeriodOrderId.value === row.id
  if (isEditing) {
    return h('div', { onClick: (e: MouseEvent) => e.stopPropagation() }, [
      h(NSelect, {
        value: row.period_code || null,
        options: periodOptions,
        size: 'small',
        clearable: false,
        filterable: true,
        placeholder: 'Указать период',
        loading: savingPeriodOrderId.value === row.id,
        style: 'width: 160px',
        onUpdateValue: (value: string | null) => onOrderPeriodChange(row, value),
        onBlur: () => {
          if (savingPeriodOrderId.value !== row.id) {
            editingPeriodOrderId.value = null
          }
        },
      }),
    ])
  }
  const label = formatOptPeriodLabel(row.period_code)
  return h(
    'span',
    {
      class: 'applications-page__period-label',
      onClick: (e: MouseEvent) => {
        e.stopPropagation()
        editingPeriodOrderId.value = row.id
      },
    },
    label === '—' ? 'Указать период' : label,
  )
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

function formatRubles(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Math.round(value))
}

function formatDateTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function paymentTagType(status: string): 'default' | 'success' | 'error' | 'warning' {
  if (status === 'paid') return 'success'
  if (status === 'partial') return 'warning'
  return 'error'
}

function groupFilterId(): number | undefined {
  if (selectedGroupKey.value === 'all') return undefined
  const n = Number(selectedGroupKey.value)
  return Number.isFinite(n) ? n : undefined
}

const groupFilterOptions = computed(() => [
  { label: 'Все группы', value: 'all' },
  ...groups.value.map((row) => ({
    value: String(row.id),
    label: row.name,
  })),
])

const columns = computed<DataTableColumns<OptOrderRegistryItem>>(() => {
  const cols: DataTableColumns<OptOrderRegistryItem> = [
    {
      title: 'Заявка',
      key: 'order',
      width: 170,
      ellipsis: { tooltip: true },
      render: (row) => `Сделка №${row.lead_id} · №${row.order_no}`,
    },
    {
      title: 'Период',
      key: 'period_code',
      width: 180,
      render: (row) => renderPeriodCell(row),
    },
    {
      title: 'Клиент',
      key: 'contact',
      minWidth: 160,
      ellipsis: { tooltip: true },
      render: (row) => row.contact_name || row.buyer.name || `ИНН ${row.buyer.inn}`,
    },
  ]
  if (canFilterManager.value) {
    cols.push({
      title: 'Менеджер',
      key: 'manager',
      width: 140,
      ellipsis: { tooltip: true },
      render: (row) => row.manager_name || '—',
    })
  }
  cols.push(
    {
      title: 'Группа',
      key: 'group',
      width: 150,
      ellipsis: { tooltip: true },
      render: (row) => row.group_name || `Группа #${row.group_id}`,
    },
    {
      title: 'Объём',
      key: 'total_volume',
      width: 120,
      align: 'right',
      render: (row) => `${formatMoney(row.total_volume)} ₽`,
    },
    {
      title: 'К оплате',
      key: 'commission_due',
      width: 130,
      align: 'right',
      render: (row) => `${formatRubles(row.commission_due)} ₽`,
    },
    {
      title: 'Оплачено',
      key: 'amount_paid',
      width: 120,
      align: 'right',
      render: (row) => `${formatRubles(row.amount_paid)} ₽`,
    },
    {
      title: 'Оплата',
      key: 'payment_status',
      width: 120,
      render: (row) =>
        h(
          NTag,
          {
            size: 'small',
            bordered: false,
            class:
              row.payment_status === 'paid'
                ? 'applications-page__pill applications-page__pill--ok'
                : row.payment_status === 'partial'
                  ? 'applications-page__pill applications-page__pill--warn'
                  : 'applications-page__pill applications-page__pill--danger',
          },
          { default: () => optPaymentStatusLabel(row.payment_status) },
        ),
    },
  )
  return cols
})

const paymentRegisterColumns = computed<DataTableColumns<OptPaymentRegisterItem>>(() => [
  { title: 'Сделка', key: 'order', width: 116, render: (r) => `№${r.lead_id} / ${r.order_no}` },
  { title: 'Клиент', key: 'client', minWidth: 190, ellipsis: { tooltip: true }, render: (r) => r.client_name || r.client_shop_name || `ИНН ${r.client_inn}` },
  { title: 'Лавок', key: 'shops', width: 90, render: (r) => `${r.lines.length} шт.` },
  { title: 'Период', key: 'period', width: 110, render: (r) => formatOptPeriodLabel(r.period_code) },
  { title: 'Объём', key: 'volume', width: 130, align: 'right', render: (r) => `${formatMoney(r.volume)} ₽` },
  { title: 'К оплате', key: 'due', width: 118, align: 'right', render: (r) => `${formatRubles(r.due_amount)} ₽` },
  { title: 'Оплачено', key: 'paid', width: 118, align: 'right', render: (r) => `${formatRubles(r.paid_amount)} ₽` },
  { title: 'Осталось', key: 'debt', width: 118, align: 'right', render: (r) => h(NTag, { size: 'small', type: r.remaining_amount > 0 ? 'warning' : 'success', bordered: false }, { default: () => `${formatRubles(r.remaining_amount)} ₽` }) },
  { title: '', key: 'detail', width: 104, render: (r) => h(NButton, { size: 'small', tertiary: true, type: 'primary', onClick: (event: MouseEvent) => { event.stopPropagation(); openPaymentRegisterDetail(r) } }, { default: () => 'Детали' }) },
])

function rowKey(row: OptOrderRegistryItem): DataTableRowKey {
  return row.id
}

function paymentRegisterRowKey(row: OptPaymentRegisterItem): DataTableRowKey {
  return row.id
}

function paymentRegisterRowProps(row: OptPaymentRegisterItem) {
  return {
    style: 'cursor: pointer',
    onClick: () => openPaymentRegisterDetail(row),
  }
}

function openPaymentRegisterDetail(row: OptPaymentRegisterItem): void {
  selectedPaymentRegister.value = row
  paymentRegisterDetailOpen.value = true
}

function rowProps(row: OptOrderRegistryItem) {
  return {
    style: 'cursor: pointer',
    onClick: () => openDetail(row),
  }
}

function openDetail(row: OptOrderRegistryItem): void {
  void router.push({
    name: 'application-detail',
    params: { leadId: String(row.lead_id), orderId: String(row.id) },
    query: {
      ...(row.chat_id != null ? { chat: String(row.chat_id) } : {}),
      ...(activeTab.value === 'benik' ? { tab: 'benik' } : {}),
    },
  })
}

function resolvedOrdersPaymentStatus(): string | undefined {
  const value = paymentStatusFilter.value
  if (value === 'all' || value == null) return undefined
  return value
}

async function loadManagers(): Promise<void> {
  if (!canFilterManager.value) {
    managers.value = []
    return
  }
  try {
    managers.value = await listOptOrderManagers({
      group_id: groupFilterId(),
      period_code: periodFilter.value || undefined,
      kind: registryKind(),
    })
    if (
      managerFilter.value != null &&
      !managers.value.some((row) => row.id === managerFilter.value)
    ) {
      managerFilter.value = null
    }
  } catch {
    managers.value = []
  }
}

async function loadGroups(): Promise<void> {
  if (!canFilterGroup.value) {
    groups.value = []
    return
  }
  try {
    const deptId = auth.isAdmin ? undefined : (auth.user?.department_id ?? undefined)
    groups.value = await listGroups(deptId)
    if (
      selectedGroupKey.value !== 'all' &&
      !groups.value.some((row) => String(row.id) === selectedGroupKey.value)
    ) {
      selectedGroupKey.value = 'all'
    }
  } catch {
    groups.value = []
  }
}

async function openBlacklist(): Promise<void> {
  blacklistOpen.value = true
  blacklistLoading.value = true
  try {
    const { data } = await http.get<{ items: typeof blacklistItems.value }>('/blacklist')
    blacklistItems.value = data.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить чёрный список')
  } finally {
    blacklistLoading.value = false
  }
}

async function addBlacklist(): Promise<void> {
  if (!blacklistValue.value.trim() || !blacklistReason.value.trim()) {
    message.warning('Укажите ник или ИНН и причину')
    return
  }
  blacklistSaving.value = true
  try {
    const { data } = await http.post('/blacklist', { kind: blacklistKind.value, value: blacklistValue.value, reason: blacklistReason.value })
    blacklistItems.value.unshift(data)
    blacklistValue.value = ''
    blacklistReason.value = ''
    message.success('Добавлено в чёрный список')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось добавить запись')
  } finally {
    blacklistSaving.value = false
  }
}

async function removeBlacklist(id: number): Promise<void> {
  try {
    await http.delete(`/blacklist/${id}`)
    blacklistItems.value = blacklistItems.value.filter((item) => item.id !== id)
    message.success('Запись удалена из чёрного списка')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось удалить запись')
  }
}

async function load(): Promise<void> {
    const hasRows = items.value.length > 0 || paymentItems.value.length > 0 || paymentRegisterItems.value.length > 0
  if (!hasRows) loading.value = true
  try {
    const common = {
      group_id: groupFilterId(),
      period_code: periodFilter.value || undefined,
      manager_user_id: canFilterManager.value ? managerFilter.value || undefined : undefined,
      q: buyerSearchApplied.value.trim() || undefined,
      offset: (page.value - 1) * pageSize,
      limit: pageSize,
    }
    if (activeTab.value === 'payments') {
      const data = await listOptPaymentRegister({
        ...common,
      })
      paymentRegisterItems.value = data.items
      paymentItems.value = []
      items.value = []
      total.value = data.total
      totalVolumeSum.value = 0
      commissionDueSum.value = 0
      amountPaidSum.value = 0
    } else {
      const data = await listOptOrdersRegistry({
        ...common,
        payment_status: resolvedOrdersPaymentStatus(),
        kind: registryKind(),
      })
      items.value = data.items
      paymentItems.value = []
      paymentRegisterItems.value = []
      total.value = data.total
      totalVolumeSum.value = Number(data.total_volume_sum ?? 0)
      commissionDueSum.value = Number(data.commission_due_sum ?? 0)
      amountPaidSum.value = Number(data.amount_paid_sum ?? 0)
    }
  } catch (err) {
    message.error(
      err instanceof AppError
        ? err.message
        : activeTab.value === 'payments'
          ? 'Не удалось загрузить оплаты'
          : activeTab.value === 'benik'
            ? 'Не удалось загрузить заявки Беника'
            : 'Не удалось загрузить заявки',
    )
    if (!hasRows) {
      items.value = []
      paymentItems.value = []
      total.value = 0
      totalVolumeSum.value = 0
      commissionDueSum.value = 0
      amountPaidSum.value = 0
    }
  } finally {
    loading.value = false
  }
}

async function onSyncWith1c(): Promise<void> {
  syncing1c.value = true
  try {
    // Sync all submitted OPT orders — no period filter required.
    const report = await syncOptOrdersWith1c(null)
    syncReport.value = report
    syncReportOpen.value = true
    const parts = [
      `без изменений: ${report.unchanged}`,
      `обновлено: ${report.updated}`,
      `восстановлено: ${report.restored}`,
      `удалено лишних: ${report.deleted_extra}`,
    ]
    if (report.errors.length) {
      message.warning(`Сверка завершена с ошибками (${report.errors.length}). ${parts.join(', ')}`)
    } else {
      message.success(`Сверка с 1С выполнена. ${parts.join(', ')}`)
    }
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось синхронизировать с 1С')
  } finally {
    syncing1c.value = false
  }
}

function goToChatFromPayment(): void {
  const chatId = selectedPayment.value?.chat_id
  if (chatId == null) {
    message.warning('У заявки нет связанного чата')
    return
  }
  void router.push({ name: 'chats', query: { chatId: String(chatId) } })
}

function applyBuyerSearch(): void {
  const next = (buyerSearch.value ?? '').trim()
  if (next === buyerSearchApplied.value && page.value === 1) {
    void load()
    return
  }
  buyerSearchApplied.value = next
  page.value = 1
}

function onTabChange(name: string | number): void {
  if (name === 'payments') activeTab.value = 'payments'
  else if (name === 'benik') activeTab.value = 'benik'
  else activeTab.value = 'orders'
  if (activeTab.value === 'payments' && paymentStatusFilter.value === 'unpaid') {
    paymentStatusFilter.value = null
  }
  page.value = 1
}

watch(
  [page, paymentStatusFilter, periodFilter, selectedGroupKey, managerFilter, activeTab, buyerSearchApplied],
  () => {
    void load()
  },
)

watchDebounced(
  buyerSearch,
  (value) => {
    const next = (value ?? '').trim()
    if (next === buyerSearchApplied.value) return
    buyerSearchApplied.value = next
    page.value = 1
  },
  { debounce: 350 },
)

watch(selectedGroupKey, () => {
  void loadManagers()
})

watch(periodFilter, () => {
  void loadManagers()
})

watch(activeTab, () => {
  if (activeTab.value !== 'payments') {
    void loadManagers()
  }
})

onMounted(() => {
  const tab = route.query.tab
  if (tab === 'benik' || tab === 'payments') activeTab.value = tab
  void loadGroups()
  void loadManagers()
  void load()
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
          <template v-else>Только ваши заявки</template>
        </p>
      </div>
      <div class="applications-page__header-actions">
        <NButton size="small" secondary type="error" @click="openBlacklist">Чёрный список</NButton>
        <NButton
          v-if="canSync1c && activeTab === 'orders'"
          size="small"
          type="primary"
          secondary
          :loading="syncing1c"
          :disabled="syncing1c"
          @click="onSyncWith1c"
        >
          Синхронизировать с 1С
        </NButton>
      </div>
    </header>

    <div class="applications-page__filters">
        <NInput
          v-model:value="buyerSearch"
          clearable
          size="small"
          placeholder="Покупатель / ИНН"
          @keyup.enter="applyBuyerSearch"
        />
        <NSelect
          v-if="canFilterGroup"
          v-model:value="selectedGroupKey"
          :options="groupFilterOptions"
          placeholder="Группа"
          size="small"
          filterable
        />
        <NSelect
          v-if="canFilterManager"
          v-model:value="managerFilter"
          :options="managerOptions"
          placeholder="Менеджер"
          size="small"
          clearable
          filterable
        />
        <NSelect
          v-model:value="periodFilter"
          :options="periodOptions"
          placeholder="Период"
          size="small"
          clearable
          filterable
        />
        <NSelect
          v-model:value="paymentStatusFilter"
          :options="paymentStatusOptions"
          :placeholder="activeTab === 'payments' ? 'Статус заявки' : 'Статус оплаты'"
          size="small"
          clearable
        />
    </div>

    <NTabs class="applications-page__tabs" :value="activeTab" type="line" @update:value="onTabChange">
      <NTabPane name="orders" tab="Заявки" />
      <NTabPane name="benik" tab="Бенефициар" />
      <NTabPane name="payments" tab="Все оплаты" />
    </NTabs>

    <div
      v-if="isOrdersLikeTab && (items.length > 0 || total > 0)"
      class="applications-page__totals"
    >
      <span class="applications-page__totals-label">
        Итого {{ totalsScopeHint }} · заявок: {{ total }}
      </span>
      <span class="applications-page__totals-metric">
        <span class="applications-page__totals-key">Объём</span>
        <strong>{{ formatMoney(totalVolumeSum) }} ₽</strong>
      </span>
      <span class="applications-page__totals-metric">
        <span class="applications-page__totals-key">К оплате</span>
        <strong>{{ formatRubles(commissionDueSum) }} ₽</strong>
      </span>
      <span class="applications-page__totals-metric">
        <span class="applications-page__totals-key">Оплачено</span>
        <strong>{{ formatRubles(amountPaidSum) }} ₽</strong>
      </span>
    </div>
    <div v-else-if="activeTab === 'payments' && paymentRegisterItems.length" class="applications-page__totals">
      <span class="applications-page__totals-label">На этой странице · строк: {{ total }}</span>
      <span class="applications-page__totals-metric"><span class="applications-page__totals-key">Объём</span><strong>{{ formatMoney(paymentRegisterTotals.volume) }} ₽</strong></span>
      <span class="applications-page__totals-metric"><span class="applications-page__totals-key">К оплате</span><strong>{{ formatRubles(paymentRegisterTotals.due) }} ₽</strong></span>
      <span class="applications-page__totals-metric"><span class="applications-page__totals-key">Оплачено</span><strong>{{ formatRubles(paymentRegisterTotals.paid) }} ₽</strong></span>
      <span class="applications-page__totals-metric"><span class="applications-page__totals-key">Осталось</span><strong>{{ formatRubles(paymentRegisterTotals.remaining) }} ₽</strong></span>
    </div>

    <NSpin class="applications-page__spin" :show="loading && items.length === 0 && paymentItems.length === 0 && paymentRegisterItems.length === 0">
      <template v-if="isOrdersLikeTab">
        <NEmpty
          v-if="!items.length && !loading"
          :description="activeTab === 'benik' ? 'Заявок Беника пока нет' : 'Заявок пока нет'"
        />
        <div v-else class="applications-page__table">
          <NDataTable
            size="small"
            flex-height
            :columns="columns"
            :data="items"
            :row-key="rowKey"
            :row-props="rowProps"
            :bordered="false"
            :pagination="false"
            :scroll-x="1200"
            virtual-scroll
            :min-row-height="VIRTUAL_DATA_TABLE_MIN_ROW_HEIGHT"
          />
        </div>
      </template>

      <template v-else>
        <NEmpty
          v-if="!paymentRegisterItems.length && !loading"
          description="Строк реестра пока нет"
        />
        <div v-else class="applications-page__table">
          <NDataTable
            size="small"
            flex-height
            :columns="paymentRegisterColumns"
            :data="paymentRegisterItems"
            :row-key="paymentRegisterRowKey"
            :row-props="paymentRegisterRowProps"
            :bordered="false"
            :pagination="false"
            :scroll-x="1100"
            virtual-scroll
            :min-row-height="VIRTUAL_DATA_TABLE_MIN_ROW_HEIGHT"
          />
        </div>
      </template>
    </NSpin>

    <div v-if="total > pageSize" class="applications-page__pager">
      <NPagination v-model:page="page" :page-size="pageSize" :item-count="total" />
    </div>

    <NModal
      v-model:show="paymentRegisterDetailOpen"
      preset="card"
      :title="selectedPaymentRegister ? `Расчёт по заявке №${selectedPaymentRegister.order_no}` : 'Расчёт'"
      :style="{ width: 'min(760px, 96vw)', maxHeight: 'calc(100vh - 32px)' }"
      class="applications-page__modal applications-page__register-modal"
    >
      <template v-if="selectedPaymentRegister">
        <dl class="applications-page__facts applications-page__facts--payment">
          <div><dt>Сделка / заявка</dt><dd>№{{ selectedPaymentRegister.lead_id }} / {{ selectedPaymentRegister.order_no }}</dd></div>
          <div><dt>Период</dt><dd>{{ formatOptPeriodLabel(selectedPaymentRegister.period_code) }}</dd></div>
          <div><dt>Менеджер</dt><dd>{{ selectedPaymentRegister.manager_name || '—' }}</dd></div>
          <div><dt>Клиент</dt><dd>{{ selectedPaymentRegister.client_name || selectedPaymentRegister.client_shop_name || '—' }} · ИНН {{ selectedPaymentRegister.client_inn }}</dd></div>
          <div><dt>ОКВЭД</dt><dd>{{ selectedPaymentRegister.client_okved || '—' }}</dd></div>
          <div><dt>Объём</dt><dd>{{ formatMoney(selectedPaymentRegister.volume) }} ₽</dd></div>
          <div><dt>К оплате / оплачено / долг</dt><dd>{{ formatRubles(selectedPaymentRegister.due_amount) }} ₽ / {{ formatRubles(selectedPaymentRegister.paid_amount) }} ₽ / {{ formatRubles(selectedPaymentRegister.remaining_amount) }} ₽</dd></div>
        </dl>
        <h3 class="applications-page__section-title">Лавки</h3>
        <div class="applications-page__register-lines">
          <div v-for="shop in selectedPaymentRegisterShops" :key="shop.inn" class="applications-page__register-line">
            <strong>{{ shop.name }}</strong>
            <span>ИНН {{ shop.inn }} · {{ shop.category }} · строк счёта: {{ shop.lines }}</span>
            <span>Объём {{ formatMoney(shop.volume) }} ₽ · к оплате {{ formatRubles(shop.due) }} ₽</span>
            <span>Бенефициару {{ formatRubles(shop.beneficiary) }} ₽ · маржа факт / план: {{ formatRubles(shop.actual) }} ₽ / {{ formatRubles(shop.planned) }} ₽</span>
          </div>
        </div>
        <div class="applications-page__modal-actions">
          <NButton @click="paymentRegisterDetailOpen = false">Закрыть</NButton>
        </div>
      </template>
    </NModal>

    <NModal v-model:show="blacklistOpen" preset="card" title="Чёрный список заявок" :style="{ width: 'min(640px, 96vw)' }">
      <p class="applications-page__muted">Заявка от указанного Telegram-ника или с ИНН лавки не будет загружена. Причина будет показана при попытке загрузки.</p>
      <div class="applications-page__blacklist-form">
        <NSelect v-model:value="blacklistKind" :options="[{ label: 'Telegram-ник человека', value: 'telegram_username' }, { label: 'ИНН лавки клиента', value: 'buyer_inn' }]" />
        <NInput v-model:value="blacklistValue" :placeholder="blacklistKind === 'telegram_username' ? '@username' : 'ИНН'" />
        <NInput v-model:value="blacklistReason" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="Почему добавлен в ЧС" />
        <NButton type="error" :loading="blacklistSaving" @click="addBlacklist">Добавить в ЧС</NButton>
      </div>
      <NSpin :show="blacklistLoading">
        <NEmpty v-if="!blacklistLoading && !blacklistItems.length" description="Чёрный список пуст" />
        <div v-else class="applications-page__blacklist-list">
          <div v-for="item in blacklistItems" :key="item.id" class="applications-page__blacklist-item">
            <div><strong>{{ item.kind === 'telegram_username' ? `@${item.value}` : `ИНН ${item.value}` }}</strong><span>{{ item.reason }}</span></div>
            <NButton size="small" quaternary type="error" @click="removeBlacklist(item.id)">Убрать</NButton>
          </div>
        </div>
      </NSpin>
    </NModal>

    <NModal
      v-model:show="paymentDetailOpen"
      preset="card"
      :title="
        selectedPayment
          ? `Оплата · сделка №${selectedPayment.lead_id} · заявка №${selectedPayment.order_no}`
          : 'Оплата'
      "
      class="applications-page__modal"
      :style="{ width: 'min(720px, 96vw)' }"
      :segmented="{ content: true, footer: 'soft' }"
    >
      <template v-if="selectedPayment">
        <dl class="applications-page__facts applications-page__facts--payment">
          <div>
            <dt>Сумма</dt>
            <dd>{{ formatRubles(selectedPayment.amount) }} ₽</dd>
          </div>
          <div>
            <dt>Дата оплаты</dt>
            <dd>{{ formatDateTime(selectedPayment.paid_at) }}</dd>
          </div>
          <div>
            <dt>Тип / получатель</dt>
            <dd>
              {{ optPaymentTypeLabel(selectedPayment.payment_type) }} ·
              {{ optPaymentRecipientLabel(selectedPayment.recipient) }}
            </dd>
          </div>
          <div>
            <dt>Внёс оплату</dt>
            <dd>
              {{ selectedPayment.created_by_name || `user #${selectedPayment.created_by}` }}
            </dd>
          </div>
          <div>
            <dt>Клиент</dt>
            <dd>{{ selectedPayment.contact_name || '—' }}</dd>
          </div>
          <div>
            <dt>Покупатель</dt>
            <dd>
              {{ selectedPayment.buyer.name || `ИНН ${selectedPayment.buyer.inn}` }}
            </dd>
          </div>
          <div>
            <dt>Менеджер карточки</dt>
            <dd>{{ selectedPayment.manager_name || '—' }}</dd>
          </div>
          <div>
            <dt>Отдел / группа</dt>
            <dd>
              {{ selectedPayment.department_name || '—' }} /
              {{ selectedPayment.group_name || `Группа #${selectedPayment.group_id}` }}
            </dd>
          </div>
          <div>
            <dt>Период</dt>
            <dd>{{ selectedPayment.period_code || '—' }}</dd>
          </div>
          <div>
            <dt>Статус заявки</dt>
            <dd>
              <NTag
                size="small"
                :type="paymentTagType(selectedPayment.order_payment_status)"
                :bordered="false"
              >
                {{ optPaymentStatusLabel(selectedPayment.order_payment_status) }}
              </NTag>
            </dd>
          </div>
          <div>
            <dt>К оплате / оплачено</dt>
            <dd>
              {{ formatRubles(selectedPayment.order_commission_due) }} ₽ /
              {{ formatRubles(selectedPayment.order_amount_paid) }} ₽
            </dd>
          </div>
        </dl>

        <div class="applications-page__payment-docs">
          <h3 class="applications-page__section-title">Подтверждение оплаты</h3>
          <OptPaymentDocuments
            v-if="selectedPaymentDocs"
            :lead-id="selectedPayment.lead_id"
            :order-id="selectedPayment.order_id"
            :payment="selectedPaymentDocs"
          />
        </div>

        <h3 class="applications-page__section-title">История оплат по заявке</h3>
        <NSpin :show="paymentHistoryLoading">
          <NEmpty
            v-if="!paymentHistory.length && !paymentHistoryLoading"
            description="История оплат пуста"
          />
          <ul v-else class="applications-page__history">
            <li
              v-for="payment in paymentHistory"
              :key="payment.id"
              :class="{
                'applications-page__history-item--active': payment.id === selectedPayment.id,
              }"
            >
              <div class="applications-page__history-top">
                <strong>{{ formatRubles(payment.amount) }} ₽</strong>
                <span>{{ formatDateTime(payment.paid_at) }}</span>
              </div>
              <p>
                {{ optPaymentTypeLabel(payment.payment_type) }} ·
                {{ optPaymentRecipientLabel(payment.recipient) }}
              </p>
              <p class="applications-page__muted">
                внёс: {{ payment.created_by_name || `user #${payment.created_by}` }}
              </p>
              <OptPaymentDocuments
                compact
                :lead-id="selectedPayment.lead_id"
                :order-id="selectedPayment.order_id"
                :payment="payment"
              />
            </li>
          </ul>
        </NSpin>
      </template>

      <template #footer>
        <div class="applications-page__footer">
          <NButton @click="paymentDetailOpen = false">Закрыть</NButton>
          <NButton
            type="primary"
            :disabled="!selectedPayment?.chat_id"
            @click="goToChatFromPayment"
          >
            <template #icon><MessageSquare :size="16" /></template>
            Перейти в чат
          </NButton>
        </div>
      </template>
    </NModal>

    <NModal
      v-model:show="syncReportOpen"
      preset="card"
      title="Сверка с 1С"
      class="applications-page__modal"
      :style="{ width: 'min(640px, 96vw)' }"
      :segmented="{ content: true, footer: 'soft' }"
    >
      <template v-if="syncReport">
        <dl class="applications-page__facts applications-page__facts--payment">
          <div>
            <dt>Период</dt>
            <dd>
              {{
                syncReport.period_code === 'all'
                  ? 'все периоды'
                  : `${syncReport.period_code} (${syncReport.period_iso})`
              }}
            </dd>
          </div>
          <div>
            <dt>Без изменений</dt>
            <dd>{{ syncReport.unchanged }}</dd>
          </div>
          <div>
            <dt>Обновлено</dt>
            <dd>{{ syncReport.updated }}</dd>
          </div>
          <div>
            <dt>Восстановлено</dt>
            <dd>{{ syncReport.restored }}</dd>
          </div>
          <div>
            <dt>Удалено лишних в 1С</dt>
            <dd>{{ syncReport.deleted_extra }}</dd>
          </div>
          <div>
            <dt>Ошибок</dt>
            <dd>{{ syncReport.errors.length }}</dd>
          </div>
        </dl>

        <template v-if="syncReport.errors.length">
          <h3 class="applications-page__section-title">Ошибки</h3>
          <ul class="applications-page__history">
            <li v-for="(row, idx) in syncReport.errors" :key="`${row.crm_id}-${idx}`">
              <div class="applications-page__history-top">
                <strong>{{ row.crm_id }}</strong>
                <span>{{ row.action }}</span>
              </div>
              <p class="applications-page__muted">{{ row.detail || '—' }}</p>
            </li>
          </ul>
        </template>
      </template>

      <template #footer>
        <div class="applications-page__footer">
          <NButton type="primary" @click="syncReportOpen = false">Закрыть</NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.applications-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
  min-width: 0;
  width: 100%;
  padding: 16px 20px 12px;
  box-sizing: border-box;
  overflow: hidden;
}

.applications-page__pager {
  display: flex;
  justify-content: flex-end;
  flex-shrink: 0;
}

.applications-page__table {
  flex: 1;
  min-height: 0;
  height: 100%;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  overflow: hidden;
  background: var(--app-surface);
}

.applications-page__table :deep(.n-data-table),
.applications-page__table :deep(.n-data-table-wrapper) {
  height: 100%;
}

.applications-page__spin {
  flex: 1 1 auto;
  min-height: 0;
}

.applications-page :deep(.applications-page__spin.n-spin-container) {
  display: flex;
  flex-direction: column;
}

.applications-page :deep(.applications-page__spin .n-spin-content) {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
  width: 100%;
}

.applications-page__totals {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: flex-end;
  gap: 10px 22px;
  padding: 10px 14px;
  border: 1px solid var(--n-border-color);
  border-radius: 10px;
  background: color-mix(in srgb, var(--n-color) 92%, var(--app-text-muted));
  font-size: 0.88rem;
  color: var(--app-text);
  flex-shrink: 0;
}

.applications-page__totals-label {
  color: var(--app-text-muted);
  margin-right: auto;
  font-size: 0.82rem;
}

.applications-page__totals-metric {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
}

.applications-page__totals-key {
  color: var(--app-text-muted);
  font-size: 0.78rem;
}

.applications-page__totals strong {
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}

.applications-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.applications-page__header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
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
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
  flex-shrink: 0;
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  background: var(--app-surface);
}

.applications-page__filters :deep(.n-input),
.applications-page__filters :deep(.n-select) {
  width: 100%;
}

.applications-page__tabs {
  flex-shrink: 0;
}

.applications-page__spin :deep(.n-empty) {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.applications-page__facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px 20px;
  margin: 0 0 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--n-border-color);
}

.applications-page__facts--payment {
  grid-template-columns: repeat(2, minmax(0, 1fr));
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

.applications-page__modal-actions {
  display: flex;
  justify-content: flex-end;
}

.applications-page__register-lines {
  display: grid;
  gap: 8px;
  margin-bottom: 16px;
}

.applications-page__register-line {
  display: grid;
  gap: 3px;
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  font-size: 0.85rem;
}

.applications-page__register-line span {
  color: var(--app-text-muted);
}

.applications-page__register-modal {
  display: flex;
  flex-direction: column;
}

.applications-page__register-modal :deep(.n-card__content) {
  overflow-y: auto;
}

.applications-page__blacklist-form {
  display: grid;
  gap: 10px;
  margin: 12px 0 16px;
}

.applications-page__blacklist-list {
  display: grid;
  gap: 8px;
}

.applications-page__blacklist-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: start;
  padding: 10px 12px;
  background: var(--app-surface-elevated);
  border-radius: 8px;
}

.applications-page__blacklist-item div {
  display: grid;
  gap: 3px;
}

.applications-page__blacklist-item span {
  color: var(--app-text-muted);
  font-size: 0.85rem;
}

.applications-page__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.applications-page__section-title {
  margin: 0 0 10px;
  font-size: 0.95rem;
  font-weight: 700;
}

.applications-page__payment-docs {
  margin: 16px 0 18px;
}

.applications-page__payment-docs .applications-page__section-title {
  margin-bottom: 8px;
}

.applications-page__history {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.applications-page__history li {
  border: 1px solid var(--n-border-color);
  border-radius: 8px;
  padding: 10px 12px;
}

.applications-page__history-item--active {
  border-color: color-mix(in srgb, var(--app-accent, #3b82f6) 55%, var(--n-border-color));
  background: color-mix(in srgb, var(--app-accent, #3b82f6) 8%, transparent);
}

.applications-page__history-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 4px;
}

.applications-page__history p {
  margin: 2px 0 0;
  font-size: 0.85rem;
}

.applications-page__history :deep(.opt-pay-docs),
.applications-page__history :deep(.opt-pay-docs__empty) {
  margin-top: 8px;
}

.applications-page__muted {
  color: var(--app-text-muted);
}

@media (max-width: 800px) {
  .applications-page__facts,
  .applications-page__facts--payment {
    grid-template-columns: 1fr;
  }
}

.applications-page__period-label {
  cursor: pointer;
  text-decoration: underline dotted;
  text-underline-offset: 2px;
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
  max-height: calc(100dvh - 24px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.applications-page__modal.n-card > .n-card-header,
.applications-page__modal.n-card > .n-card__footer {
  flex-shrink: 0;
}

.applications-page__modal.n-card > .n-card__content,
.applications-page__modal .n-card__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
}

.applications-page__pill.n-tag {
  --n-color: transparent !important;
  --n-text-color: #fff !important;
  border: 0 !important;
  color: #fff !important;
  font-weight: 700;
}

.applications-page__pill--ok.n-tag {
  background: #1a7f37 !important;
}

.applications-page__pill--danger.n-tag {
  background: #cf222e !important;
}

.applications-page__pill--warn.n-tag {
  background: #9a6700 !important;
}
</style>
