<script setup lang="ts">
import type { DataTableColumns, SelectOption } from 'naive-ui'
import {
  NButton,
  NDataTable,
  NInput,
  NPagination,
  NSelect,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  useMessage,
} from 'naive-ui'
import { Calculator, Download, RefreshCw } from 'lucide-vue-next'
import { computed, h, onMounted, ref, watch } from 'vue'

import {
  downloadAccountingRegistry,
  downloadRequirementPdf,
  listAccountingAssignments,
  listAccountingOrders,
  listAccountingRequirements,
  listAccountingUnits,
  saveBlob,
  updateAccountingAssignments,
} from '@/features/accounting/api'
import type {
  AccountingAssignment,
  AccountingOrderLine,
  AccountingRequirement,
  AccountingUnit,
} from '@/features/accounting/types'
import {
  OPT_PAYMENT_STATUS_LABELS,
  OPT_STATUS_LABELS,
} from '@/features/accounting/types'
import { AppError } from '@/shared/api/http'
import AppCard from '@/shared/ui/AppCard.vue'

const message = useMessage()

const loading = ref(false)
const activeTab = ref('orders')
const units = ref<AccountingUnit[]>([])
const isChief = ref(false)
const assignments = ref<AccountingAssignment[]>([])

const orders = ref<AccountingOrderLine[]>([])
const ordersTotal = ref(0)
const ordersPage = ref(1)
const ordersPageSize = 50
const orderSupplierInn = ref<string | null>(null)
const orderStatus = ref<string | null>(null)
const orderSearch = ref('')

const requirements = ref<AccountingRequirement[]>([])
const requirementsTotal = ref(0)
const requirementsPage = ref(1)
const requirementsPageSize = 50
const reqSupplierInn = ref<string | null>(null)
const reqStatus = ref<string | null>(null)
const reqSearch = ref('')

const downloadingRegistryId = ref<number | null>(null)
const downloadingReqId = ref<number | null>(null)
const savingAssignmentUserId = ref<number | null>(null)

const unitOptions = computed<SelectOption[]>(() =>
  units.value.map((unit) => ({
    label: unit.name ? `${unit.name} (${unit.inn})` : unit.inn,
    value: unit.inn,
  })),
)

const unitIdOptions = computed<SelectOption[]>(() =>
  units.value.map((unit) => ({
    label: unit.name ? `${unit.name} (${unit.inn})` : unit.inn,
    value: unit.id,
  })),
)

const orderStatusOptions: SelectOption[] = [
  { label: 'Все статусы', value: '' },
  { label: 'В 1С', value: 'submitted' },
  { label: 'В очереди', value: 'queued' },
  { label: 'Ошибка', value: 'failed' },
  { label: 'Черновик', value: 'draft' },
]

function formatMoney(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 2,
  }).format(value)
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('ru-RU')
}

function supplierLabel(supplier: { inn: string; name?: string | null }): string {
  return supplier.name ? `${supplier.name} · ${supplier.inn}` : supplier.inn
}

async function loadUnits(): Promise<void> {
  const data = await listAccountingUnits()
  units.value = data.items
  isChief.value = data.is_chief
}

async function loadOrders(): Promise<void> {
  loading.value = true
  try {
    const data = await listAccountingOrders({
      supplier_inn: orderSupplierInn.value || undefined,
      status: orderStatus.value || undefined,
      q: orderSearch.value.trim() || undefined,
      limit: ordersPageSize,
      offset: (ordersPage.value - 1) * ordersPageSize,
    })
    orders.value = data.items
    ordersTotal.value = data.total
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить заявки')
  } finally {
    loading.value = false
  }
}

async function loadRequirements(): Promise<void> {
  loading.value = true
  try {
    const data = await listAccountingRequirements({
      supplier_inn: reqSupplierInn.value || undefined,
      status: reqStatus.value || undefined,
      q: reqSearch.value.trim() || undefined,
      limit: requirementsPageSize,
      offset: (requirementsPage.value - 1) * requirementsPageSize,
    })
    requirements.value = data.items
    requirementsTotal.value = data.total
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить требования')
  } finally {
    loading.value = false
  }
}

async function loadAssignments(): Promise<void> {
  if (!isChief.value) return
  try {
    const data = await listAccountingAssignments()
    assignments.value = data.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить назначения')
  }
}

async function refreshAll(): Promise<void> {
  loading.value = true
  try {
    await loadUnits()
    if (activeTab.value === 'orders') await loadOrders()
    else if (activeTab.value === 'requirements') await loadRequirements()
    else await loadAssignments()
  } finally {
    loading.value = false
  }
}

async function onDownloadRegistry(row: AccountingOrderLine): Promise<void> {
  downloadingRegistryId.value = row.order_id
  try {
    const blob = await downloadAccountingRegistry(row.order_id)
    const filename = row.source_filename || `registry_${row.crm_id}.xlsx`
    saveBlob(blob, filename.endsWith('.xlsx') ? filename : `${filename}.xlsx`)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать реестр')
  } finally {
    downloadingRegistryId.value = null
  }
}

async function onDownloadRequirement(row: AccountingRequirement): Promise<void> {
  downloadingReqId.value = row.id
  try {
    const blob = await downloadRequirementPdf(row.id)
    saveBlob(blob, row.pdf_filename || `requirement_${row.external_id}.pdf`)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать PDF')
  } finally {
    downloadingReqId.value = null
  }
}

async function onAssignmentChange(userId: number, unitIds: number[]): Promise<void> {
  savingAssignmentUserId.value = userId
  try {
    const updated = await updateAccountingAssignments(userId, unitIds)
    const idx = assignments.value.findIndex((item) => item.user_id === userId)
    if (idx >= 0) assignments.value[idx] = updated
    message.success('Назначения сохранены')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить')
  } finally {
    savingAssignmentUserId.value = null
  }
}

const orderColumns = computed<DataTableColumns<AccountingOrderLine>>(() => [
  {
    title: 'Дата',
    key: 'created_at',
    width: 140,
    render: (row) => formatDate(row.created_at),
  },
  {
    title: 'Сделка / заявка',
    key: 'lead_id',
    width: 130,
    render: (row) => `№${row.lead_id} · З${row.order_no}`,
  },
  {
    title: 'Лавка',
    key: 'supplier',
    minWidth: 200,
    render: (row) => supplierLabel(row.supplier),
  },
  {
    title: 'Покупатель',
    key: 'buyer',
    minWidth: 180,
    render: (row) => row.buyer_name || row.buyer_inn,
  },
  {
    title: 'Сумма строки',
    key: 'amount',
    width: 130,
    render: (row) => formatMoney(row.amount),
  },
  {
    title: 'Статус',
    key: 'status',
    width: 110,
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: row.status === 'submitted' ? 'success' : 'default' },
        { default: () => OPT_STATUS_LABELS[row.status] || row.status },
      ),
  },
  {
    title: 'Оплата',
    key: 'payment_status',
    width: 110,
    render: (row) => OPT_PAYMENT_STATUS_LABELS[row.payment_status] || row.payment_status,
  },
  {
    title: 'Менеджер',
    key: 'manager_full_name',
    minWidth: 160,
    render: (row) => row.manager_full_name || '—',
  },
  {
    title: 'Контакт',
    key: 'contact_name',
    minWidth: 140,
    render: (row) => row.contact_name || '—',
  },
  {
    title: 'Реестр',
    key: 'registry',
    width: 110,
    render: (row) =>
      h(
        NButton,
        {
          size: 'small',
          quaternary: true,
          loading: downloadingRegistryId.value === row.order_id,
          onClick: () => onDownloadRegistry(row),
        },
        {
          icon: () => h(Download, { size: 14 }),
          default: () => 'XLSX',
        },
      ),
  },
])

const requirementColumns = computed<DataTableColumns<AccountingRequirement>>(() => [
  {
    title: 'Получено',
    key: 'received_at',
    width: 150,
    render: (row) => formatDate(row.received_at),
  },
  {
    title: 'Лавка',
    key: 'supplier',
    minWidth: 200,
    render: (row) => supplierLabel(row.supplier),
  },
  {
    title: 'Требование',
    key: 'title',
    minWidth: 220,
    render: (row) => row.title,
  },
  {
    title: 'Статус',
    key: 'status',
    width: 100,
    render: (row) => row.status,
  },
  {
    title: 'PDF',
    key: 'pdf',
    width: 110,
    render: (row) =>
      row.has_pdf
        ? h(
            NButton,
            {
              size: 'small',
              quaternary: true,
              loading: downloadingReqId.value === row.id,
              onClick: () => onDownloadRequirement(row),
            },
            {
              icon: () => h(Download, { size: 14 }),
              default: () => 'Скачать',
            },
          )
        : '—',
  },
])

watch(activeTab, async (tab) => {
  if (tab === 'orders') await loadOrders()
  else if (tab === 'requirements') await loadRequirements()
  else await loadAssignments()
})

watch([ordersPage, orderSupplierInn, orderStatus], () => {
  if (activeTab.value === 'orders') void loadOrders()
})

watch([requirementsPage, reqSupplierInn, reqStatus], () => {
  if (activeTab.value === 'requirements') void loadRequirements()
})

onMounted(async () => {
  await refreshAll()
})
</script>

<template>
  <div class="accounting-page">
    <header class="accounting-page__header">
      <div>
        <h1 class="accounting-page__title">
          <Calculator :size="22" />
          Бухгалтерия
        </h1>
        <p class="accounting-page__subtitle">
          Заявки и реестры по лавкам, требования от внешних сервисов. Менеджер указан для связи по
          каждой заявке.
        </p>
      </div>
      <NButton :loading="loading" @click="refreshAll">
        <template #icon>
          <RefreshCw :size="16" />
        </template>
        Обновить
      </NButton>
    </header>

    <AppCard>
      <NTabs v-model:value="activeTab" type="line" animated>
        <NTabPane name="orders" tab="Заявки">
          <div class="accounting-page__filters">
            <NSelect
              v-model:value="orderSupplierInn"
              :options="unitOptions"
              clearable
              filterable
              placeholder="Лавка"
              style="min-width: 260px"
            />
            <NSelect
              v-model:value="orderStatus"
              :options="orderStatusOptions"
              placeholder="Статус"
              style="width: 160px"
            />
            <NInput
              v-model:value="orderSearch"
              clearable
              placeholder="Поиск: ИНН, CRM, менеджер..."
              style="min-width: 240px"
              @keyup.enter="loadOrders"
            />
            <NButton type="primary" @click="loadOrders">Найти</NButton>
          </div>
          <NSpin :show="loading">
            <NDataTable
              :columns="orderColumns"
              :data="orders"
              :bordered="false"
              :scroll-x="1200"
              size="small"
            />
            <div class="accounting-page__pagination">
              <NPagination
                v-model:page="ordersPage"
                :page-size="ordersPageSize"
                :item-count="ordersTotal"
              />
            </div>
          </NSpin>
        </NTabPane>

        <NTabPane name="requirements" tab="Требования">
          <div class="accounting-page__filters">
            <NSelect
              v-model:value="reqSupplierInn"
              :options="unitOptions"
              clearable
              filterable
              placeholder="Лавка"
              style="min-width: 260px"
            />
            <NInput
              v-model:value="reqSearch"
              clearable
              placeholder="Поиск по названию или ID"
              style="min-width: 240px"
              @keyup.enter="loadRequirements"
            />
            <NButton type="primary" @click="loadRequirements">Найти</NButton>
          </div>
          <NSpin :show="loading">
            <NDataTable
              :columns="requirementColumns"
              :data="requirements"
              :bordered="false"
              :scroll-x="900"
              size="small"
            />
            <div class="accounting-page__pagination">
              <NPagination
                v-model:page="requirementsPage"
                :page-size="requirementsPageSize"
                :item-count="requirementsTotal"
              />
            </div>
          </NSpin>
        </NTabPane>

        <NTabPane v-if="isChief" name="assignments" tab="Назначения лавок">
          <p class="accounting-page__hint">
            Главный бухгалтер видит все лавки. Здесь можно ограничить доступ других бухгалтеров —
            пока список пуст, обычный бухгалтер не увидит заявки.
          </p>
          <div v-for="item in assignments" :key="item.user_id" class="accounting-page__assignment">
            <div class="accounting-page__assignment-name">{{ item.user_full_name }}</div>
            <NSelect
              :value="item.unit_ids"
              :options="unitIdOptions"
              multiple
              filterable
              placeholder="Лавки бухгалтера"
              :loading="savingAssignmentUserId === item.user_id"
              @update:value="(value) => onAssignmentChange(item.user_id, value as number[])"
            />
          </div>
        </NTabPane>
      </NTabs>
    </AppCard>
  </div>
</template>

<style scoped>
.accounting-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 20px 24px;
}

.accounting-page__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.accounting-page__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 1.35rem;
}

.accounting-page__subtitle {
  margin: 6px 0 0;
  color: var(--app-text-muted);
  font-size: 0.9rem;
  max-width: 720px;
}

.accounting-page__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}

.accounting-page__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.accounting-page__hint {
  margin: 0 0 12px;
  color: var(--app-text-muted);
  font-size: 0.85rem;
}

.accounting-page__assignment {
  display: grid;
  grid-template-columns: minmax(160px, 220px) 1fr;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.accounting-page__assignment-name {
  font-weight: 600;
}
</style>
