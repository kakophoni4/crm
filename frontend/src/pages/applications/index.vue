<script setup lang="ts">
import type { DataTableColumns, DataTableRowKey, SelectOption } from 'naive-ui'
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

import { listGroups, type Group } from '@/features/admin/api'
import {
  listOptOrderManagers,
  listOptOrders,
  listOptOrdersRegistry,
  listOptPaymentsLedger,
  patchOptOrderPeriod,
  syncOptOrdersWith1c,
} from '@/features/leads/opt-api'
import type {
  OptOrderRegistryItem,
  OptPayment,
  OptPaymentLedgerItem,
  OptRegistryManagerItem,
  OptSync1cResponse,
} from '@/features/leads/opt-types'
import {
  optPaymentRecipientLabel,
  optPaymentStatusLabel,
  optPaymentTypeLabel,
} from '@/features/leads/opt-types'
import { OPT_PERIOD_OPTIONS } from '@/features/leads/order-fields'
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
const periodFilter = ref<string | null>(null)
const selectedGroupKey = ref<string>('all')
const managerFilter = ref<number | null>(null)
const groups = ref<Group[]>([])
const managers = ref<OptRegistryManagerItem[]>([])
const periodOptions = OPT_PERIOD_OPTIONS
const savingPeriodOrderId = ref<number | null>(null)
const syncing1c = ref(false)
const syncReportOpen = ref(false)
const syncReport = ref<OptSync1cResponse | null>(null)

const canFilterGroup = computed(
  () => auth.isAdmin || auth.isSenior || auth.isGroupSenior,
)
const canFilterManager = computed(() => auth.isAdmin || auth.isSenior)
const canSync1c = computed(() => auth.isAdmin)

const detailOpen = ref(false)
const selected = ref<OptOrderRegistryItem | null>(null)

const paymentDetailOpen = ref(false)
const selectedPayment = ref<OptPaymentLedgerItem | null>(null)
const paymentHistoryLoading = ref(false)
const paymentHistory = ref<OptPayment[]>([])

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
    if (selected.value?.id === row.id) {
      selected.value.period_code = updated.period_code
    }
    message.success('Период сохранён')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить период')
  } finally {
    savingPeriodOrderId.value = null
  }
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
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
      render: (row) =>
        h('div', { onClick: (e: MouseEvent) => e.stopPropagation() }, [
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
          }),
        ]),
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
      title: 'К оплате',
      key: 'commission_due',
      width: 130,
      align: 'right',
      render: (row) => `${formatMoney(row.commission_due)} ₽`,
    },
    {
      title: 'Оплачено',
      key: 'amount_paid',
      width: 120,
      align: 'right',
      render: (row) => `${formatMoney(row.amount_paid)} ₽`,
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

const paymentColumns = computed<DataTableColumns<OptPaymentLedgerItem>>(() => {
  const cols: DataTableColumns<OptPaymentLedgerItem> = [
    {
      title: 'Дата',
      key: 'paid_at',
      width: 140,
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
      render: (row) =>
        `${optPaymentTypeLabel(row.payment_type)} · ${optPaymentRecipientLabel(row.recipient)}`,
    },
    {
      title: 'Сделка',
      key: 'deal',
      render: (row) => `Сделка №${row.lead_id} · №${row.order_no}`,
    },
    {
      title: 'Клиент',
      key: 'contact',
      ellipsis: { tooltip: true },
      render: (row) => row.contact_name || row.buyer.name || `ИНН ${row.buyer.inn}`,
    },
  ]
  if (canFilterManager.value) {
    cols.push({
      title: 'Менеджер карточки',
      key: 'manager',
      ellipsis: { tooltip: true },
      render: (row) => row.manager_name || '—',
    })
  }
  cols.push(
    {
      title: 'Внёс оплату',
      key: 'created_by',
      ellipsis: { tooltip: true },
      render: (row) => row.created_by_name || `user #${row.created_by}`,
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
  )
  return cols
})

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
    onClick: () => openPaymentDetail(row),
  }
}

function openDetail(row: OptOrderRegistryItem): void {
  selected.value = row
  detailOpen.value = true
}

async function openPaymentDetail(row: OptPaymentLedgerItem): Promise<void> {
  selectedPayment.value = row
  paymentDetailOpen.value = true
  paymentHistory.value = []
  paymentHistoryLoading.value = true
  try {
    const orders = await listOptOrders(row.lead_id)
    const order = orders.find((item) => item.id === row.order_id) ?? null
    paymentHistory.value = [...(order?.payments ?? [])].sort(
      (a, b) => new Date(b.paid_at).getTime() - new Date(a.paid_at).getTime(),
    )
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить историю оплат')
  } finally {
    paymentHistoryLoading.value = false
  }
}

function resolvedOrdersPaymentStatus(): string | undefined {
  const value = paymentStatusFilter.value
  if (value === 'all' || value == null) return undefined
  return value
}

function resolvedLedgerPaymentStatus(): string {
  const value = paymentStatusFilter.value
  if (value === 'partial' || value === 'paid') return value
  return 'partial,paid'
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

async function load(): Promise<void> {
  const hasRows = items.value.length > 0 || paymentItems.value.length > 0
  if (!hasRows) loading.value = true
  try {
    const common = {
      group_id: groupFilterId(),
      period_code: periodFilter.value || undefined,
      manager_user_id: canFilterManager.value ? managerFilter.value || undefined : undefined,
      offset: (page.value - 1) * pageSize,
      limit: pageSize,
    }
    if (activeTab.value === 'payments') {
      const data = await listOptPaymentsLedger({
        ...common,
        payment_status: resolvedLedgerPaymentStatus(),
      })
      paymentItems.value = data.items
      items.value = []
      total.value = data.total
    } else {
      const data = await listOptOrdersRegistry({
        ...common,
        payment_status: resolvedOrdersPaymentStatus(),
      })
      items.value = data.items
      paymentItems.value = []
      total.value = data.total
    }
  } catch (err) {
    message.error(
      err instanceof AppError
        ? err.message
        : activeTab.value === 'payments'
          ? 'Не удалось загрузить оплаты'
          : 'Не удалось загрузить заявки',
    )
    if (!hasRows) {
      items.value = []
      paymentItems.value = []
      total.value = 0
    }
  } finally {
    loading.value = false
  }
}

async function onSyncWith1c(): Promise<void> {
  if (!periodFilter.value) {
    message.warning('Выберите период для сверки с 1С')
    return
  }
  syncing1c.value = true
  try {
    const report = await syncOptOrdersWith1c(periodFilter.value)
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

function onDetailPaymentsChanged(): void {
  void load()
}

function goToChatFromOrder(): void {
  const chatId = selected.value?.chat_id
  if (chatId == null) {
    message.warning('У заявки нет связанного чата')
    return
  }
  void router.push({ name: 'chats', query: { chatId: String(chatId) } })
}

function goToChatFromPayment(): void {
  const chatId = selectedPayment.value?.chat_id
  if (chatId == null) {
    message.warning('У заявки нет связанного чата')
    return
  }
  void router.push({ name: 'chats', query: { chatId: String(chatId) } })
}

function onTabChange(name: string | number): void {
  activeTab.value = name === 'payments' ? 'payments' : 'orders'
  if (activeTab.value === 'payments' && paymentStatusFilter.value === 'unpaid') {
    paymentStatusFilter.value = null
  }
  page.value = 1
}

watch([page, paymentStatusFilter, periodFilter, selectedGroupKey, managerFilter, activeTab], () => {
  void load()
})

watch(selectedGroupKey, () => {
  void loadManagers()
})

watch(periodFilter, () => {
  void loadManagers()
})

onMounted(() => {
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
          <template v-else>Данные вашей группы</template>
        </p>
      </div>
      <div class="applications-page__filters">
        <NSelect
          v-if="canFilterGroup"
          v-model:value="selectedGroupKey"
          :options="groupFilterOptions"
          placeholder="Группа"
          style="width: 220px"
          size="small"
          filterable
        />
        <NSelect
          v-if="canFilterManager"
          v-model:value="managerFilter"
          :options="managerOptions"
          placeholder="Менеджер"
          style="width: 220px"
          size="small"
          clearable
          filterable
        />
        <NSelect
          v-model:value="periodFilter"
          :options="periodOptions"
          placeholder="Период"
          style="width: 200px"
          size="small"
          clearable
          filterable
        />
        <NSelect
          v-model:value="paymentStatusFilter"
          :options="paymentStatusOptions"
          :placeholder="activeTab === 'payments' ? 'Статус заявки' : 'Статус оплаты'"
          style="width: 200px"
          size="small"
          clearable
        />
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

    <NTabs :value="activeTab" type="line" @update:value="onTabChange">
      <NTabPane name="orders" tab="Заявки" />
      <NTabPane name="payments" tab="Все оплаты" />
    </NTabs>

    <NSpin :show="loading && items.length === 0 && paymentItems.length === 0">
      <template v-if="activeTab === 'orders'">
        <NEmpty v-if="!items.length && !loading" description="Заявок пока нет" />
        <AppCard v-else class="applications-page__card">
          <NDataTable
            size="small"
            :columns="columns"
            :data="items"
            :row-key="rowKey"
            :row-props="rowProps"
            :bordered="false"
            :pagination="false"
            :scroll-x="1180"
          />
        </AppCard>
      </template>

      <template v-else>
        <NEmpty
          v-if="!paymentItems.length && !loading"
          description="Проведённых оплат пока нет"
        />
        <AppCard v-else class="applications-page__card">
          <NDataTable
            size="small"
            :columns="paymentColumns"
            :data="paymentItems"
            :row-key="paymentRowKey"
            :row-props="paymentRowProps"
            :bordered="false"
            :pagination="false"
            :scroll-x="1280"
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
        <div class="applications-page__meta">
          <span>{{ selected.contact_name || '—' }}</span>
          <span class="applications-page__meta-sep">·</span>
          <span>{{ selected.manager_name || 'менеджер не назначен' }}</span>
          <span class="applications-page__meta-sep">·</span>
          <span>{{ selected.group_name || `Группа #${selected.group_id}` }}</span>
          <span class="applications-page__meta-sep">·</span>
          <span class="applications-page__meta-buyer">
            {{ selected.buyer.name || `ИНН ${selected.buyer.inn}` }}
          </span>
        </div>

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
          <NButton type="primary" :disabled="!selected?.chat_id" @click="goToChatFromOrder">
            <template #icon><MessageSquare :size="16" /></template>
            Перейти в чат
          </NButton>
        </div>
      </template>
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
            <dd>{{ formatMoney(selectedPayment.amount) }} ₽</dd>
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
              {{ formatMoney(selectedPayment.order_commission_due) }} ₽ /
              {{ formatMoney(selectedPayment.order_amount_paid) }} ₽
            </dd>
          </div>
        </dl>

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
                <strong>{{ formatMoney(payment.amount) }} ₽</strong>
                <span>{{ formatDateTime(payment.paid_at) }}</span>
              </div>
              <p>
                {{ optPaymentTypeLabel(payment.payment_type) }} ·
                {{ optPaymentRecipientLabel(payment.recipient) }}
              </p>
              <p class="applications-page__muted">
                внёс: {{ payment.created_by_name || `user #${payment.created_by}` }}
              </p>
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
            <dd>{{ syncReport.period_code }} ({{ syncReport.period_iso }})</dd>
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
  gap: 16px;
  padding: 16px 20px 24px;
  min-height: 0;
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
}

.applications-page__card {
  min-width: 0;
  overflow: hidden;
}

.applications-page__panel {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
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

.applications-page__pager {
  display: flex;
  justify-content: flex-end;
}

.applications-page__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 6px;
  margin: 0 0 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--n-border-color);
  font-size: 0.82rem;
  color: var(--app-text-muted);
}

.applications-page__meta-sep {
  opacity: 0.5;
}

.applications-page__meta-buyer {
  color: var(--app-text);
  font-weight: 600;
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

.applications-page__muted {
  color: var(--app-text-muted);
}

@media (max-width: 800px) {
  .applications-page__facts,
  .applications-page__facts--payment {
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
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.applications-page__modal.n-card > .n-card-header,
.applications-page__modal.n-card > .n-card__footer {
  flex-shrink: 0;
}

.applications-page__modal.n-card > .n-card__content {
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
