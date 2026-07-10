<script setup lang="ts">
import type { DataTableColumns, SelectOption } from 'naive-ui'
import {
  NButton,
  NCollapse,
  NCollapseItem,
  NDataTable,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NPagination,
  NSelect,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  useMessage,
} from 'naive-ui'
import { Calculator, Download, Eye, Plus, RefreshCw } from 'lucide-vue-next'
import { computed, h, onMounted, onUnmounted, ref, watch } from 'vue'

import {
  assignAccountingUnitOwner,
  createAccountingUnit,
  downloadAccountingRegistry,
  downloadRequirementPdf,
  listAccountingOrders,
  listAccountingRequirements,
  listAccountingUnitCategories,
  listAccountingUnitOwners,
  listAccountingUnits,
  saveBlob,
  syncAccountingRequirements,
} from '@/features/accounting/api'
import type {
  AccountingOrderLineBrief,
  AccountingRequirement,
  AccountingUnit,
  AccountingUnitCategory,
  AccountingUnitOrder,
  AccountingUnitOrderGroup,
  AccountingUnitOwnerRow,
} from '@/features/accounting/types'
import {
  formatAccountingMoney,
  formatAccountingPayment,
} from '@/features/accounting/types'
import { AppError } from '@/shared/api/http'
import AppCard from '@/shared/ui/AppCard.vue'
import AttachmentPreviewModal from '@/widgets/chat/AttachmentPreviewModal.vue'

const message = useMessage()

const loading = ref(false)
const syncingRequirements = ref(false)
const activeTab = ref('orders')
const isChief = ref(false)
const units = ref<AccountingUnit[]>([])

const orderGroups = ref<AccountingUnitOrderGroup[]>([])
const ordersTotal = ref(0)
const ordersPage = ref(1)
const ordersPageSize = 20
const orderSupplierInn = ref<string | null>(null)
const orderSearch = ref('')
const expandedLavki = ref<string[]>([])

const requirements = ref<AccountingRequirement[]>([])
const requirementsTotal = ref(0)
const requirementsPage = ref(1)
const requirementsPageSize = 50
const reqSupplierInn = ref<string | null>(null)
const reqSearch = ref('')

const unitOwners = ref<AccountingUnitOwnerRow[]>([])
const accountantOptions = ref<SelectOption[]>([])
const savingUnitId = ref<number | null>(null)

const categories = ref<AccountingUnitCategory[]>([])
const categoryOptions = computed<SelectOption[]>(() =>
  categories.value.map((cat) => ({
    label:
      cat.base_rate_percent != null
        ? `${cat.label} · базовая ${cat.base_rate_percent}%`
        : cat.label,
    value: cat.code,
  })),
)

interface CreateUnitForm {
  inn: string
  kpp: string
  name: string
  category_code: string | null
  commission_rate_percent: number | null
}

function emptyCreateForm(): CreateUnitForm {
  return { inn: '', kpp: '', name: '', category_code: null, commission_rate_percent: null }
}

const createOpen = ref(false)
const createSaving = ref(false)
const createForm = ref<CreateUnitForm>(emptyCreateForm())

function openCreateUnit(): void {
  createForm.value = emptyCreateForm()
  createOpen.value = true
}

async function submitCreateUnit(): Promise<void> {
  const form = createForm.value
  const inn = form.inn.trim()
  const kpp = form.kpp.trim()
  const name = form.name.trim()
  if (!/^\d{10}$|^\d{12}$/.test(inn)) {
    message.warning('ИНН должен содержать 10 или 12 цифр')
    return
  }
  if (kpp && !/^\d{9}$/.test(kpp)) {
    message.warning('КПП должен содержать 9 цифр')
    return
  }
  if (!name) {
    message.warning('Укажите название лавки')
    return
  }
  if (!form.category_code) {
    message.warning('Выберите тип компании')
    return
  }
  if (form.commission_rate_percent == null || form.commission_rate_percent < 0) {
    message.warning('Укажите процент')
    return
  }
  createSaving.value = true
  try {
    await createAccountingUnit({
      inn,
      ...(kpp ? { kpp } : {}),
      name,
      category_code: form.category_code,
      commission_rate_percent: form.commission_rate_percent,
    })
    message.success('Лавка добавлена')
    createOpen.value = false
    await loadUnits()
    if (isChief.value) await loadUnitOwners()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось добавить лавку')
  } finally {
    createSaving.value = false
  }
}

const downloadingRegistryId = ref<number | null>(null)
const downloadingReqId = ref<number | null>(null)
const previewOpen = ref(false)
const previewOrder = ref<AccountingUnitOrder | null>(null)
const previewBlob = ref<Blob | null>(null)
const previewBlobUrl = ref<string | null>(null)
const previewLoading = ref(false)
const previewLabel = ref('Реестр.xlsx')

const unitOptions = computed<SelectOption[]>(() =>
  units.value.map((unit) => ({
    label: unit.name ? `${unit.name} (${unit.inn})` : unit.inn,
    value: unit.inn,
  })),
)

function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('ru-RU')
}

function formatDocumentDate(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString('ru-RU')
}

function registryFilename(order: AccountingUnitOrder): string {
  const raw = order.source_filename || `registry_${order.crm_id}.xlsx`
  return raw.endsWith('.xlsx') ? raw : `${raw}.xlsx`
}

function clearPreviewBlob(): void {
  if (previewBlobUrl.value) {
    URL.revokeObjectURL(previewBlobUrl.value)
    previewBlobUrl.value = null
  }
  previewBlob.value = null
}

function closeRegistryPreview(): void {
  previewOpen.value = false
  previewOrder.value = null
  clearPreviewBlob()
}

async function openPreview(order: AccountingUnitOrder): Promise<void> {
  previewOrder.value = order
  previewLabel.value = registryFilename(order)
  previewOpen.value = true
  previewLoading.value = true
  clearPreviewBlob()
  try {
    const blob = await downloadAccountingRegistry(order.order_id)
    previewBlob.value = blob
    previewBlobUrl.value = URL.createObjectURL(blob)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить реестр')
    closeRegistryPreview()
  } finally {
    previewLoading.value = false
  }
}

function lavkaTitle(unit: AccountingUnitOrderGroup['unit']): string {
  return unit.name ? `${unit.name} · ${unit.inn}` : unit.inn
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
      q: orderSearch.value.trim() || undefined,
      limit: ordersPageSize,
      offset: (ordersPage.value - 1) * ordersPageSize,
    })
    orderGroups.value = data.items
    ordersTotal.value = data.total
    if (expandedLavki.value.length === 0 && data.items.length > 0) {
      expandedLavki.value = [data.items[0].unit.inn]
    }
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

async function onSyncRequirements(): Promise<void> {
  syncingRequirements.value = true
  try {
    const result = await syncAccountingRequirements()
    const parts = [
      `забрано ${result.fetched}`,
      `новых ${result.created}`,
      `уже было ${result.existing}`,
      `ошибок ${result.failed}`,
    ]
    if (result.failed > 0 && result.errors.length) {
      message.warning(`${parts.join(', ')}. ${result.errors[0]}`)
    } else {
      message.success(parts.join(', '))
    }
    await loadRequirements()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось синхронизировать требования')
  } finally {
    syncingRequirements.value = false
  }
}

async function loadUnitOwners(): Promise<void> {
  if (!isChief.value) return
  try {
    const data = await listAccountingUnitOwners()
    unitOwners.value = data.items
    accountantOptions.value = data.accountants.map((item) => ({
      label: item.full_name,
      value: item.user_id,
    }))
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить лавки')
  }
}

async function refreshAll(): Promise<void> {
  loading.value = true
  try {
    await loadUnits()
    if (activeTab.value === 'orders') await loadOrders()
    else if (activeTab.value === 'requirements') await loadRequirements()
    else await loadUnitOwners()
  } finally {
    loading.value = false
  }
}

async function onDownloadRegistry(order: AccountingUnitOrder): Promise<void> {
  downloadingRegistryId.value = order.order_id
  try {
    const blob = await downloadAccountingRegistry(order.order_id)
    const filename = order.source_filename || `registry_${order.crm_id}.xlsx`
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

async function onAssignUnit(row: AccountingUnitOwnerRow, value: number | null): Promise<void> {
  savingUnitId.value = row.unit_id
  try {
    const updated = await assignAccountingUnitOwner(row.unit_id, value)
    const idx = unitOwners.value.findIndex((item) => item.unit_id === row.unit_id)
    if (idx >= 0) unitOwners.value[idx] = updated
    unitOwners.value = [...unitOwners.value].sort((a, b) => {
      const aKey = a.accountant_user_id == null ? 0 : 1
      const bKey = b.accountant_user_id == null ? 0 : 1
      if (aKey !== bKey) return aKey - bKey
      return (a.name || a.inn).localeCompare(b.name || b.inn, 'ru')
    })
    message.success('Назначение сохранено')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить')
  } finally {
    savingUnitId.value = null
  }
}

function renderLinesTable(lines: AccountingOrderLineBrief[]) {
  return h('table', { class: 'accounting-page__lines-table' }, [
    h('thead', [
      h('tr', [
        h('th', '№'),
        h('th', 'Дата'),
        h('th', 'Сумма'),
        h('th', 'Док. 1С'),
      ]),
    ]),
    h(
      'tbody',
      lines.map((line) =>
        h('tr', { key: line.line_id }, [
          h('td', String(line.line_no)),
          h('td', formatDocumentDate(line.document_date)),
          h('td', formatAccountingMoney(line.amount)),
          h('td', line.document_number || '—'),
        ]),
      ),
    ),
  ])
}

function orderColumns(): DataTableColumns<AccountingUnitOrder> {
  return [
    {
      type: 'expand',
      expandable: (row) => row.line_count > 0,
      renderExpand: (row) => renderLinesTable(row.lines),
    },
    {
      title: 'Дата загрузки',
      key: 'created_at',
      width: 130,
      render: (row) => formatDate(row.created_at),
    },
    {
      title: 'Заявка',
      key: 'lead_id',
      width: 150,
      render: (row) =>
        h('div', { class: 'accounting-page__deal-cell' }, [
          h('span', { class: 'accounting-page__deal-main' }, `Заявка №${row.order_no}`),
          h('span', { class: 'accounting-page__deal-sub' }, `сделка №${row.lead_id}`),
        ]),
    },
    {
      title: 'Файл',
      key: 'source_filename',
      minWidth: 140,
      ellipsis: { tooltip: true },
      render: (row) => row.source_filename || row.crm_id,
    },
    {
      title: 'Покупатель',
      key: 'buyer_name',
      minWidth: 160,
      ellipsis: { tooltip: true },
      render: (row) => row.buyer_name || row.buyer_inn,
    },
    {
      title: 'Объём по лавке',
      key: 'lavka_line_volume',
      width: 130,
      render: (row) => formatAccountingMoney(row.lavka_line_volume),
    },
    {
      title: 'Оплата',
      key: 'payment_status',
      width: 150,
      render: (row) =>
        formatAccountingPayment(row.amount_paid, row.commission_due, row.payment_status),
    },
    {
      title: 'Менеджер',
      key: 'manager_full_name',
      minWidth: 120,
      render: (row) => row.manager_full_name || '—',
    },
    {
      title: 'Реестр',
      key: 'registry',
      width: 150,
      render: (row) =>
        h('div', { class: 'accounting-page__registry-actions' }, [
          h(
            NButton,
            {
              size: 'small',
              quaternary: true,
              onClick: () => openPreview(row),
            },
            {
              icon: () => h(Eye, { size: 14 }),
              default: () => 'Просмотр',
            },
          ),
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
        ]),
    },
  ]
}

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
    render: (row) =>
      row.supplier.name ? `${row.supplier.name} · ${row.supplier.inn}` : row.supplier.inn,
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
  else await loadUnitOwners()
})

watch([ordersPage, orderSupplierInn], () => {
  if (activeTab.value === 'orders') void loadOrders()
})

watch([requirementsPage, reqSupplierInn], () => {
  if (activeTab.value === 'requirements') void loadRequirements()
})

async function loadCategories(): Promise<void> {
  try {
    categories.value = await listAccountingUnitCategories()
  } catch {
    categories.value = []
  }
}

onMounted(async () => {
  await Promise.all([refreshAll(), loadCategories()])
})

onUnmounted(() => {
  clearPreviewBlob()
})
</script>

<template>
  <div class="accounting-page">
    <header class="accounting-page__header">
      <h1 class="accounting-page__title">
        <Calculator :size="22" />
        Бухгалтерия
      </h1>
      <div class="accounting-page__header-actions">
        <NButton v-if="isChief" type="primary" @click="openCreateUnit">
          <template #icon>
            <Plus :size="16" />
          </template>
          Добавить лавку
        </NButton>
        <NButton :loading="loading" @click="refreshAll">
          <template #icon>
            <RefreshCw :size="16" />
          </template>
          Обновить
        </NButton>
      </div>
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
            <NEmpty v-if="!loading && orderGroups.length === 0" description="Нет заявок" />
            <NCollapse v-else v-model:expanded-names="expandedLavki">
              <NCollapseItem
                v-for="group in orderGroups"
                :key="group.unit.inn"
                :name="group.unit.inn"
              >
                <template #header>
                  <div class="accounting-page__lavka-header">
                    <span class="accounting-page__lavka-title">{{ lavkaTitle(group.unit) }}</span>
                    <NTag size="small" :bordered="false">
                      {{ group.orders.length }}
                      {{ group.orders.length === 1 ? 'заявка' : 'заявок' }}
                    </NTag>
                  </div>
                </template>
                <NDataTable
                  :columns="orderColumns()"
                  :data="group.orders"
                  :bordered="false"
                  :row-key="(row: AccountingUnitOrder) => row.order_id"
                  size="small"
                  :scroll-x="1100"
                />
              </NCollapseItem>
            </NCollapse>
            <div v-if="ordersTotal > ordersPageSize" class="accounting-page__pagination">
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
            <NInput
              v-model:value="reqSearch"
              clearable
              placeholder="Поиск по названию или ID"
              style="min-width: 240px"
              @keyup.enter="loadRequirements"
            />
            <NButton type="primary" @click="loadRequirements">Найти</NButton>
            <NButton
              :loading="syncingRequirements"
              @click="onSyncRequirements"
            >
              <template #icon><RefreshCw :size="16" /></template>
              Забрать из СБИС
            </NButton>
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
          <NSpin :show="loading">
            <NEmpty
              v-if="!loading && unitOwners.length === 0"
              description="Нет активных лавок"
            />
            <div v-else class="accounting-page__owners">
              <div
                v-for="row in unitOwners"
                :key="row.unit_id"
                class="accounting-page__owner-row"
                :class="{ 'accounting-page__owner-row--unassigned': row.accountant_user_id == null }"
              >
                <div class="accounting-page__owner-lavka">
                  <span class="accounting-page__owner-name">{{ row.name || row.inn }}</span>
                  <span class="accounting-page__owner-inn">{{ row.inn }}</span>
                </div>
                <NSelect
                  :value="row.accountant_user_id"
                  :options="accountantOptions"
                  clearable
                  filterable
                  placeholder="Бухгалтер"
                  :loading="savingUnitId === row.unit_id"
                  style="min-width: 260px"
                  @update:value="(value) => onAssignUnit(row, value as number | null)"
                />
              </div>
            </div>
          </NSpin>
        </NTabPane>
      </NTabs>
    </AppCard>

    <AttachmentPreviewModal
      :open="previewOpen"
      :loading="previewLoading"
      :label="previewLabel"
      :blob-url="previewBlobUrl"
      :blob="previewBlob"
      preview-kind="spreadsheet"
      @close="closeRegistryPreview"
    />

    <NModal
      v-model:show="createOpen"
      preset="card"
      title="Новая лавка"
      style="width: 480px; max-width: 92vw"
    >
      <NForm label-placement="top" @submit.prevent="submitCreateUnit">
        <NFormItem label="ИНН" required>
          <NInput
            v-model:value="createForm.inn"
            placeholder="10 или 12 цифр"
            :allow-input="(v: string) => /^\d*$/.test(v)"
            maxlength="12"
          />
        </NFormItem>
        <NFormItem label="КПП">
          <NInput
            v-model:value="createForm.kpp"
            placeholder="9 цифр (необязательно)"
            :allow-input="(v: string) => /^\d*$/.test(v)"
            maxlength="9"
          />
        </NFormItem>
        <NFormItem label="Название" required>
          <NInput v-model:value="createForm.name" placeholder="Название лавки" />
        </NFormItem>
        <NFormItem label="Тип компании" required>
          <NSelect
            v-model:value="createForm.category_code"
            :options="categoryOptions"
            placeholder="Выберите тип"
          />
        </NFormItem>
        <NFormItem label="Процент комиссии" required>
          <NInputNumber
            v-model:value="createForm.commission_rate_percent"
            :min="0"
            :max="100"
            :precision="2"
            :step="0.1"
            placeholder="Например, 2.7"
            style="width: 100%"
          >
            <template #suffix>%</template>
          </NInputNumber>
        </NFormItem>
      </NForm>
      <template #footer>
        <div class="accounting-page__modal-actions">
          <NButton @click="createOpen = false">Отмена</NButton>
          <NButton type="primary" :loading="createSaving" @click="submitCreateUnit">
            Добавить
          </NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.accounting-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 16px;
}

.accounting-page__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.accounting-page__header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.accounting-page__modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.accounting-page__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.accounting-page__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.accounting-page__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.accounting-page__lavka-header {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.accounting-page__lavka-title {
  font-weight: 600;
}

.accounting-page__deal-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.accounting-page__deal-main {
  font-weight: 500;
}

.accounting-page__deal-sub {
  font-size: 0.75rem;
  color: var(--app-text-muted);
}

.accounting-page__registry-actions {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.accounting-page__lines-table {
  width: 100%;
  border-collapse: collapse;
  margin: 4px 0 8px 36px;
  max-width: calc(100% - 36px);
  font-size: 0.8rem;
}

.accounting-page__lines-table th,
.accounting-page__lines-table td {
  padding: 6px 10px;
  text-align: left;
  border-bottom: 1px solid var(--app-border);
}

.accounting-page__lines-table th {
  color: var(--app-text-muted);
  font-weight: 500;
}

.accounting-page__lines-table td:nth-child(3) {
  text-align: right;
  white-space: nowrap;
}

.accounting-page__owners {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.accounting-page__owner-row {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(260px, 320px);
  gap: 16px;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--app-surface-elevated);
}

.accounting-page__owner-row--unassigned {
  background: var(--app-warning-soft);
}

.accounting-page__owner-lavka {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.accounting-page__owner-name {
  font-weight: 600;
}

.accounting-page__owner-inn {
  font-size: 0.8rem;
  color: var(--app-text-muted);
}
</style>
