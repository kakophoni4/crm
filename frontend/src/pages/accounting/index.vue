<script setup lang="ts">
import type { DataTableColumns, SelectOption } from 'naive-ui'
import {
  NButton,
  NCollapse,
  NCollapseItem,
  NDataTable,
  NDatePicker,
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
  NUpload,
  useDialog,
  useMessage,
} from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import {
  Calculator,
  CalendarRange,
  Download,
  Eye,
  MailOpen,
  Percent,
  Plus,
  RefreshCw,
  Undo2,
} from 'lucide-vue-next'
import { computed, h, onMounted, onUnmounted, ref, watch } from 'vue'

import {
  assignAccountingUnitOwner,
  createAccountingUnit,
  deleteAccountingUnit,
  downloadAccountingRegistry,
  downloadRequirementPdf,
  listAccountingOrders,
  patchAccountingOrderPeriod,
  listAccountingRequirements,
  listAccountingUnitCategories,
  listAccountingUnitOwners,
  listAccountingUnits,
  createTaskFromRequirement,
  patchAccountingRequirementStatus,
  patchAccountingUnit,
  replyAccountingRequirement,
  saveBlob,
  syncAccountingRequirements,
} from '@/features/accounting/api'
import { uploadFile } from '@/features/chats/api'
import { formatTaskAssigneeLabel, listTaskAssignees } from '@/features/tasks/api'
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
import { formatOptPeriodLabel, OPT_PERIOD_OPTIONS } from '@/features/leads/order-fields'
import { AppError } from '@/shared/api/http'
import type { AttachmentPreviewKind } from '@/shared/lib/attachment-preview-kind'
import { peekCached, setCached } from '@/shared/lib/stale-cache'
import AppCard from '@/shared/ui/AppCard.vue'
import AttachmentPreviewModal from '@/widgets/chat/AttachmentPreviewModal.vue'
import { useAuthStore } from '@/shared/store/auth'

const message = useMessage()
const dialog = useDialog()
const auth = useAuthStore()

/** Полное юр.имя → короткое «ООО „АФИНА“». */
function shortLavkaName(name: string | null | undefined): string {
  const raw = (name || '').trim()
  if (!raw) return ''
  const quoted = raw.match(/[«"“„]([^»"”]+)[»"”]/)
  if (quoted?.[1]?.trim()) {
    const inner = quoted[1].trim()
    if (/общество\s+с\s+ограниченной\s+ответственностью|ооо/i.test(raw)) {
      return `ООО «${inner}»`
    }
    return inner
  }
  return raw
    .replace(/Общество\s+с\s+ограниченной\s+ответственностью/gi, 'ООО')
    .replace(/\s+/g, ' ')
    .trim()
}

function lavkaLabel(name: string | null | undefined, inn: string): string {
  const short = shortLavkaName(name)
  return short ? `${short} · ${inn}` : inn
}

const ordersLoading = ref(false)
const requirementsLoading = ref(false)
const ownersLoading = ref(false)
const syncingRequirements = ref(false)
const activeTab = ref('orders')
const isChief = ref(false)
const units = ref<AccountingUnit[]>([])
const anyLoading = computed(
  () => ordersLoading.value || requirementsLoading.value || ownersLoading.value,
)

const ORDERS_CACHE_KEY = 'accounting:orders:default'
const REQUIREMENTS_CACHE_PREFIX = 'accounting:requirements:'

const orderGroups = ref<AccountingUnitOrderGroup[]>([])
const ordersTotal = ref(0)
const ordersPage = ref(1)
const ordersPageSize = 20
const orderSupplierInn = ref<string | null>(null)
const orderPeriodCode = ref<string | null>(null)
const orderSearch = ref('')
const expandedLavki = ref<string[]>([])
const periodFilterOptions = OPT_PERIOD_OPTIONS
const savingPeriodOrderId = ref<number | null>(null)
const editingPeriodOrderId = ref<number | null>(null)

async function onOrderPeriodChange(
  row: AccountingUnitOrder,
  value: string | null,
): Promise<void> {
  if (!value || value === row.period_code) return
  savingPeriodOrderId.value = row.order_id
  try {
    const updated = await patchAccountingOrderPeriod(row.order_id, value)
    for (const group of orderGroups.value) {
      const item = group.orders.find((order) => order.order_id === row.order_id)
      if (item) item.period_code = updated.period_code
    }
    message.success('Период сохранён')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить период')
  } finally {
    savingPeriodOrderId.value = null
    editingPeriodOrderId.value = null
  }
}

function renderOrderPeriodCell(row: AccountingUnitOrder) {
  const isEditing =
    editingPeriodOrderId.value === row.order_id || savingPeriodOrderId.value === row.order_id
  if (isEditing) {
    return h('div', { onClick: (e: MouseEvent) => e.stopPropagation() }, [
      h(NSelect, {
        value: row.period_code || null,
        options: periodFilterOptions,
        size: 'small',
        clearable: false,
        filterable: true,
        placeholder: 'Указать период',
        loading: savingPeriodOrderId.value === row.order_id,
        style: 'min-width: 160px',
        onUpdateValue: (value: string | null) => onOrderPeriodChange(row, value),
        onBlur: () => {
          if (savingPeriodOrderId.value !== row.order_id) {
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
      class: 'accounting-page__period-label',
      onClick: (e: MouseEvent) => {
        e.stopPropagation()
        editingPeriodOrderId.value = row.order_id
      },
    },
    label === '—' ? 'Указать период' : label,
  )
}

const requirements = ref<AccountingRequirement[]>([])
const requirementsTotal = ref(0)
const requirementsPage = ref(1)
const requirementsPageSize = 20
const reqSupplierInn = ref<string | null>(null)
const reqSearch = ref('')
const requirementsStatusTab = ref<'new' | 'answered' | 'replied'>('new')
const answeringReqId = ref<number | null>(null)
const expandedReqLavki = ref<string[]>([])

interface RequirementLavkaGroup {
  inn: string
  name: string | null
  items: AccountingRequirement[]
}

function requirementCountLabel(n: number): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return 'требование'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'требования'
  return 'требований'
}

const requirementGroupsAll = computed<RequirementLavkaGroup[]>(() => {
  const map = new Map<string, RequirementLavkaGroup>()
  for (const row of requirements.value) {
    const inn = row.supplier.inn || '—'
    const existing = map.get(inn)
    if (existing) {
      existing.items.push(row)
      if (!existing.name && row.supplier.name) existing.name = row.supplier.name
    } else {
      map.set(inn, {
        inn,
        name: row.supplier.name || null,
        items: [row],
      })
    }
  }
  return [...map.values()].sort((a, b) =>
    (shortLavkaName(a.name) || a.name || a.inn).localeCompare(
      shortLavkaName(b.name) || b.name || b.inn,
      'ru',
    ),
  )
})

const requirementGroupsTotal = computed(() => requirementGroupsAll.value.length)

const requirementGroups = computed(() => {
  const start = (requirementsPage.value - 1) * requirementsPageSize
  return requirementGroupsAll.value.slice(start, start + requirementsPageSize)
})

const unitOwners = ref<AccountingUnitOwnerRow[]>([])
const accountantOptions = ref<SelectOption[]>([])
const savingUnitId = ref<number | null>(null)
const assignmentsSubTab = ref<'selling' | 'requirements'>('selling')
const togglingUnitId = ref<number | null>(null)
const deletingUnitId = ref<number | null>(null)

const sellingUnitOwners = computed(() =>
  unitOwners.value.filter((row) => row.is_active !== false),
)
const requirementUnitOwners = computed(() =>
  unitOwners.value.filter((row) => row.is_active === false),
)

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
  period_codes: string[]
}

function emptyCreateForm(): CreateUnitForm {
  return {
    inn: '',
    kpp: '',
    name: '',
    category_code: null,
    commission_rate_percent: null,
    period_codes: [],
  }
}

const periodOptions = OPT_PERIOD_OPTIONS

const createOpen = ref(false)
const createSaving = ref(false)
const createForm = ref<CreateUnitForm>(emptyCreateForm())

const rateEditOpen = ref(false)
const rateEditSaving = ref(false)
const rateEditUnitId = ref<number | null>(null)
const rateEditLabel = ref('')
const rateEditValue = ref<number | null>(null)

const limitEditOpen = ref(false)
const limitEditSaving = ref(false)
const limitEditUnitId = ref<number | null>(null)
const limitEditLabel = ref('')
const limitEditValue = ref<number | null>(null)

function sumGroupVolume(group: AccountingUnitOrderGroup): number {
  return group.orders.reduce((acc, row) => acc + Number(row.lavka_line_volume || 0), 0)
}

const periodsEditOpen = ref(false)
const periodsEditSaving = ref(false)
const periodsEditUnitId = ref<number | null>(null)
const periodsEditLabel = ref('')
const periodsEditValue = ref<string[]>([])

function openCreateUnit(): void {
  createForm.value = emptyCreateForm()
  createOpen.value = true
}

function openCreateUnitFromGroup(unit: {
  inn: string
  kpp?: string | null
  name?: string | null
  commission_rate_percent?: number | null
}): void {
  createForm.value = {
    ...emptyCreateForm(),
    inn: unit.inn,
    kpp: unit.kpp?.trim() || '',
    name: unit.name?.trim() || '',
    commission_rate_percent:
      unit.commission_rate_percent != null ? Number(unit.commission_rate_percent) : null,
    period_codes: orderPeriodCode.value ? [orderPeriodCode.value] : [],
  }
  createOpen.value = true
  message.info('Лавки ещё нет в справочнике — заполните тип и сохраните, чтобы править % и лимит')
}

function catalogUnitId(unit: { id?: number; unit_id?: number }): number | null {
  const id = unit.id ?? unit.unit_id
  return id != null && id > 0 ? id : null
}

function formatRateButtonLabel(rate: number | null | undefined): string {
  if (rate == null) return '+ %'
  return `${Number(rate)}%`
}

function openEditRate(unit: {
  id?: number
  unit_id?: number
  name?: string | null
  inn: string
  kpp?: string | null
  commission_rate_percent?: number | null
}): void {
  const id = catalogUnitId(unit)
  if (id == null) {
    openCreateUnitFromGroup(unit)
    return
  }
  rateEditUnitId.value = id
  rateEditLabel.value = lavkaLabel(unit.name, unit.inn)
  rateEditValue.value =
    unit.commission_rate_percent != null ? Number(unit.commission_rate_percent) : null
  rateEditOpen.value = true
}

async function submitEditRate(): Promise<void> {
  if (rateEditUnitId.value == null) return
  if (rateEditValue.value == null || rateEditValue.value < 0 || rateEditValue.value > 100) {
    message.warning('Укажите процент от 0 до 100')
    return
  }
  rateEditSaving.value = true
  try {
    await patchAccountingUnit(rateEditUnitId.value, {
      commission_rate_percent: rateEditValue.value,
    })
    message.success('Процент обновлён')
    rateEditOpen.value = false
    await Promise.all([loadUnits(), loadOrders()])
    if (isChief.value) await loadUnitOwners()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить процент')
  } finally {
    rateEditSaving.value = false
  }
}

function openEditLimit(unit: {
  id?: number
  unit_id?: number
  name?: string | null
  inn: string
  kpp?: string | null
  commission_rate_percent?: number | null
  volume_limit?: number | null
}): void {
  const id = catalogUnitId(unit)
  if (id == null) {
    openCreateUnitFromGroup(unit)
    return
  }
  limitEditUnitId.value = id
  limitEditLabel.value = lavkaLabel(unit.name, unit.inn)
  limitEditValue.value =
    unit.volume_limit != null ? Number(unit.volume_limit) : null
  limitEditOpen.value = true
}

async function submitEditLimit(): Promise<void> {
  if (limitEditUnitId.value == null) return
  if (limitEditValue.value != null && limitEditValue.value < 0) {
    message.warning('Лимит не может быть отрицательным')
    return
  }
  limitEditSaving.value = true
  try {
    if (limitEditValue.value == null) {
      await patchAccountingUnit(limitEditUnitId.value, { clear_volume_limit: true })
    } else {
      await patchAccountingUnit(limitEditUnitId.value, {
        volume_limit: limitEditValue.value,
      })
    }
    message.success(limitEditValue.value == null ? 'Лимит снят' : 'Лимит обновлён')
    limitEditOpen.value = false
    await Promise.all([loadUnits(), loadOrders()])
    if (isChief.value) await loadUnitOwners()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить лимит')
  } finally {
    limitEditSaving.value = false
  }
}

function openEditPeriods(row: AccountingUnitOwnerRow): void {
  periodsEditUnitId.value = row.unit_id
  periodsEditLabel.value = lavkaLabel(row.name, row.inn)
  periodsEditValue.value = [...(row.period_codes || [])]
  periodsEditOpen.value = true
}

async function submitEditPeriods(): Promise<void> {
  if (periodsEditUnitId.value == null) return
  if (!periodsEditValue.value.length) {
    message.warning('Укажите хотя бы один период')
    return
  }
  periodsEditSaving.value = true
  try {
    const updated = await patchAccountingUnit(periodsEditUnitId.value, {
      period_codes: periodsEditValue.value,
    })
    message.success('Периоды обновлены')
    periodsEditOpen.value = false
    const idx = unitOwners.value.findIndex((item) => item.unit_id === periodsEditUnitId.value)
    if (idx >= 0) {
      unitOwners.value[idx] = {
        ...unitOwners.value[idx],
        period_codes: updated.period_codes || periodsEditValue.value,
      }
    }
    await loadUnits()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить периоды')
  } finally {
    periodsEditSaving.value = false
  }
}

function formatPeriodCodes(codes: string[] | null | undefined): string {
  if (!codes?.length) return 'периоды не заданы'
  return codes.join(', ')
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
  if (!form.period_codes.length) {
    message.warning('Укажите хотя бы один разрешённый период')
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
      period_codes: form.period_codes,
    })
    message.success('Лавка добавлена')
    createOpen.value = false
    await Promise.all([loadUnits(), loadOrders()])
    if (isChief.value) await loadUnitOwners()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось добавить лавку')
  } finally {
    createSaving.value = false
  }
}

const downloadingRegistryId = ref<number | null>(null)
const downloadingReqId = ref<number | null>(null)
const previewingReqId = ref<number | null>(null)
const previewOpen = ref(false)
const previewOrder = ref<AccountingUnitOrder | null>(null)
const previewBlob = ref<Blob | null>(null)
const previewBlobUrl = ref<string | null>(null)
const previewLoading = ref(false)
const previewLabel = ref('Реестр.xlsx')
const previewKind = ref<AttachmentPreviewKind>('spreadsheet')

const unitOptions = computed<SelectOption[]>(() =>
  units.value.map((unit) => ({
    label: lavkaLabel(unit.name, unit.inn),
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

function closePreview(): void {
  previewOpen.value = false
  previewOrder.value = null
  previewingReqId.value = null
  clearPreviewBlob()
}

async function openPreview(order: AccountingUnitOrder): Promise<void> {
  previewOrder.value = order
  previewKind.value = 'spreadsheet'
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
    closePreview()
  } finally {
    previewLoading.value = false
  }
}

async function openRequirementPreview(row: AccountingRequirement): Promise<void> {
  if (!row.has_pdf) return
  previewingReqId.value = row.id
  previewKind.value = 'pdf'
  previewLabel.value = row.pdf_filename || `requirement_${row.external_id}.pdf`
  previewOpen.value = true
  previewLoading.value = true
  clearPreviewBlob()
  try {
    const blob = await downloadRequirementPdf(row.id)
    const pdfBlob =
      blob.type === 'application/pdf' ? blob : new Blob([blob], { type: 'application/pdf' })
    previewBlob.value = pdfBlob
    previewBlobUrl.value = URL.createObjectURL(pdfBlob)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось открыть PDF')
    closePreview()
  } finally {
    previewLoading.value = false
    previewingReqId.value = null
  }
}

function lavkaTitle(unit: AccountingUnitOrderGroup['unit']): string {
  return lavkaLabel(unit.name, unit.inn)
}

function formatUnitRate(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${Number(value)}%`
}

async function loadUnits(): Promise<void> {
  const data = await listAccountingUnits()
  units.value = data.items
  isChief.value = data.is_chief
}

function ordersCacheKey(): string {
  return [
    'accounting:orders',
    orderSupplierInn.value || '',
    orderPeriodCode.value || '',
    orderSearch.value.trim(),
    String(ordersPage.value),
  ].join(':')
}

function requirementsCacheKey(): string {
  return [
    REQUIREMENTS_CACHE_PREFIX + requirementsStatusTab.value,
    reqSupplierInn.value || '',
    reqSearch.value.trim(),
  ].join(':')
}

async function loadOrders(): Promise<void> {
  if (!orderGroups.value.length) ordersLoading.value = true
  try {
    const data = await listAccountingOrders({
      supplier_inn: orderSupplierInn.value || undefined,
      period_code: orderPeriodCode.value || undefined,
      q: orderSearch.value.trim() || undefined,
      limit: ordersPageSize,
      offset: (ordersPage.value - 1) * ordersPageSize,
    })
    orderGroups.value = data.items
    ordersTotal.value = data.total
    setCached(ordersCacheKey(), { items: data.items, total: data.total })
    if (
      !orderSupplierInn.value &&
      !orderPeriodCode.value &&
      !orderSearch.value.trim() &&
      ordersPage.value === 1
    ) {
      setCached(ORDERS_CACHE_KEY, { items: data.items, total: data.total })
    }
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить заявки')
  } finally {
    ordersLoading.value = false
  }
}

async function loadRequirements(): Promise<void> {
  if (!requirements.value.length) requirementsLoading.value = true
  try {
    const pageSize = 200
    const items: AccountingRequirement[] = []
    let total = 0
    let offset = 0
    for (;;) {
      const data = await listAccountingRequirements({
        supplier_inn: reqSupplierInn.value || undefined,
        status: requirementsStatusTab.value,
        q: reqSearch.value.trim() || undefined,
        limit: pageSize,
        offset,
      })
      total = data.total
      items.push(...data.items)
      if (items.length >= total || data.items.length < pageSize) break
      offset += pageSize
    }
    requirements.value = items
    requirementsTotal.value = total
    const maxPage = Math.max(1, Math.ceil(requirementGroupsAll.value.length / requirementsPageSize) || 1)
    if (requirementsPage.value > maxPage) requirementsPage.value = maxPage
    setCached(requirementsCacheKey(), { items, total })
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить требования')
  } finally {
    requirementsLoading.value = false
  }
}

async function onSyncRequirements(): Promise<void> {
  syncingRequirements.value = true
  try {
    const result = await syncAccountingRequirements()
    if (result.queued) {
      message.success('Синхронизация запущена в фоне. Обновите список через 1–2 минуты.')
      window.setTimeout(() => {
        void loadRequirements()
      }, 60_000)
      return
    }
    const parts = [
      `забрано ${result.fetched}`,
      `новых ${result.created}`,
      `уже было ${result.existing}`,
      `ошибок ${result.failed}`,
    ]
    if (result.skipped_non_pdf) {
      parts.push(`пропущено не-PDF ${result.skipped_non_pdf}`)
    }
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

async function onSetRequirementStatus(
  row: AccountingRequirement,
  status: 'new' | 'answered',
): Promise<void> {
  answeringReqId.value = row.id
  try {
    await patchAccountingRequirementStatus(row.id, status)
    message.success(
      status === 'answered' ? 'Отмечено как прочитанное' : 'Вернуто в непрочитанные',
    )
    await loadRequirements()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось обновить статус')
  } finally {
    answeringReqId.value = null
  }
}

const replyModalOpen = ref(false)
const replyTarget = ref<AccountingRequirement | null>(null)
const replyFiles = ref<File[]>([])
const replySending = ref(false)
const taskModalOpen = ref(false)
const taskTarget = ref<AccountingRequirement | null>(null)
const taskAssigneeId = ref<number | null>(null)
const taskUnitInn = ref<string | null>(null)
const taskTitle = ref('')
const taskDescription = ref('')
const taskDueAt = ref<number | null>(null)
const taskAssigneeOptions = ref<{ label: string; value: number }[]>([])
const taskFiles = ref<File[]>([])
const taskSaving = ref(false)

const taskUnitOptions = computed(() =>
  units.value.map((u) => ({
    label: lavkaLabel(u.name, u.inn),
    value: u.inn,
  })),
)

/** +N рабочих дней (пн–пт) со следующего календарного дня — как на бэке. */
function addWorkingDaysMs(startMs: number, days: number): number {
  const cur = new Date(startMs)
  cur.setHours(0, 0, 0, 0)
  let left = days
  while (left > 0) {
    cur.setDate(cur.getDate() + 1)
    const wd = cur.getDay()
    if (wd !== 0 && wd !== 6) left -= 1
  }
  cur.setHours(18, 0, 0, 0)
  return cur.getTime()
}

function defaultTaskDueFromRequirement(row: AccountingRequirement): number {
  if (row.response_due_date) {
    const d = new Date(`${row.response_due_date}T18:00:00`)
    if (!Number.isNaN(d.getTime())) return d.getTime()
  }
  const received = new Date(row.received_at || row.created_at)
  const base = Number.isNaN(received.getTime()) ? Date.now() : received.getTime()
  return addWorkingDaysMs(base, 5)
}

function openReplyModal(row: AccountingRequirement): void {
  replyTarget.value = row
  replyFiles.value = []
  replyModalOpen.value = true
}

function onReplyUploadChange(options: { fileList: UploadFileInfo[] }): void {
  replyFiles.value = options.fileList
    .map((f) => f.file)
    .filter((f): f is File => f instanceof File)
}

async function submitReply(dryRun: boolean): Promise<void> {
  if (!replyTarget.value) return
  if (!replyFiles.value.length) {
    message.warning('Прикрепите файлы ответа')
    return
  }
  replySending.value = true
  try {
    const result = await replyAccountingRequirement(
      replyTarget.value.id,
      replyFiles.value,
      dryRun,
    )
    if (dryRun) {
      message.success(result.success ? 'Проверка OK — можно отправлять' : 'Проверка не прошла')
    } else {
      message.success(result.success ? 'Ответ отправлен в ФНС' : 'Ошибка отправки')
      if (result.success) replyModalOpen.value = false
      await loadRequirements()
    }
    if (result.reply_error) message.warning(result.reply_error)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось отправить ответ')
  } finally {
    replySending.value = false
  }
}

function onTaskUploadChange(options: { fileList: UploadFileInfo[] }): void {
  taskFiles.value = options.fileList
    .map((f) => f.file)
    .filter((f): f is File => f instanceof File)
}

async function openTaskFromReqModal(row: AccountingRequirement): Promise<void> {
  const short = shortLavkaName(row.supplier.name) || row.supplier.inn
  taskTarget.value = row
  taskTitle.value = `Требование ФНС · ${short}`
  taskDescription.value = ''
  taskAssigneeId.value = auth.user?.id ?? null
  taskUnitInn.value = row.supplier.inn || null
  taskDueAt.value = defaultTaskDueFromRequirement(row)
  taskFiles.value = []
  taskModalOpen.value = true
  if (!units.value.length) {
    try {
      const data = await listAccountingUnits()
      units.value = data.items
    } catch {
      /* keep empty */
    }
  }
  try {
    const data = await listTaskAssignees()
    const meId = auth.user?.id
    taskAssigneeOptions.value = data.map((u) => ({
      label: formatTaskAssigneeLabel(u, meId),
      value: u.id,
    }))
    if (meId != null && !taskAssigneeOptions.value.some((o) => o.value === meId)) {
      taskAssigneeOptions.value.unshift({
        label: `Себе (${auth.user?.full_name || 'я'})`,
        value: meId,
      })
    }
  } catch {
    taskAssigneeOptions.value = []
  }
}

function assignTaskToSelf(): void {
  const meId = auth.user?.id
  if (meId == null) return
  taskAssigneeId.value = meId
}

async function submitTaskFromReq(): Promise<void> {
  if (!taskTarget.value || taskAssigneeId.value == null) {
    message.warning('Выберите исполнителя')
    return
  }
  if (!taskUnitInn.value) {
    message.warning('Выберите лавку')
    return
  }
  taskSaving.value = true
  try {
    const fileIds: number[] = []
    for (const file of taskFiles.value) {
      const uploaded = await uploadFile(file)
      fileIds.push(uploaded.id)
    }
    await createTaskFromRequirement(taskTarget.value.id, {
      unit_inn: taskUnitInn.value,
      assignee_id: taskAssigneeId.value,
      title: taskTitle.value.trim(),
      description: taskDescription.value.trim() || null,
      due_at: taskDueAt.value ? new Date(taskDueAt.value).toISOString() : null,
      file_ids: fileIds,
    })
    message.success('Задача создана')
    taskModalOpen.value = false
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось создать задачу')
  } finally {
    taskSaving.value = false
  }
}

async function loadUnitOwners(): Promise<void> {
  if (!isChief.value) return
  if (!unitOwners.value.length) ownersLoading.value = true
  try {
    const data = await listAccountingUnitOwners()
    unitOwners.value = data.items
    accountantOptions.value = data.accountants.map((item) => ({
      label: item.full_name,
      value: item.user_id,
    }))
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить лавки')
  } finally {
    ownersLoading.value = false
  }
}

async function refreshAll(): Promise<void> {
  await loadUnits()
  if (activeTab.value === 'orders') await loadOrders()
  else if (activeTab.value === 'requirements') await loadRequirements()
  else await loadUnitOwners()
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

function sortUnitOwners(rows: AccountingUnitOwnerRow[]): AccountingUnitOwnerRow[] {
  return [...rows].sort((a, b) => {
    const aActive = a.is_active !== false ? 0 : 1
    const bActive = b.is_active !== false ? 0 : 1
    if (aActive !== bActive) return aActive - bActive
    const aKey = a.accountant_user_id == null ? 0 : 1
    const bKey = b.accountant_user_id == null ? 0 : 1
    if (aKey !== bKey) return aKey - bKey
    return (a.name || a.inn).localeCompare(b.name || b.inn, 'ru')
  })
}

async function onAssignUnit(row: AccountingUnitOwnerRow, value: number | null): Promise<void> {
  savingUnitId.value = row.unit_id
  try {
    const updated = await assignAccountingUnitOwner(row.unit_id, value)
    const idx = unitOwners.value.findIndex((item) => item.unit_id === row.unit_id)
    if (idx >= 0) unitOwners.value[idx] = updated
    unitOwners.value = sortUnitOwners(unitOwners.value)
    message.success('Назначение сохранено')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить')
  } finally {
    savingUnitId.value = null
  }
}

async function onToggleUnitActive(row: AccountingUnitOwnerRow, nextActive: boolean): Promise<void> {
  togglingUnitId.value = row.unit_id
  try {
    const updated = await patchAccountingUnit(row.unit_id, { is_active: nextActive })
    const idx = unitOwners.value.findIndex((item) => item.unit_id === row.unit_id)
    if (idx >= 0) {
      unitOwners.value[idx] = {
        ...unitOwners.value[idx],
        is_active: updated.is_active,
        period_codes: updated.period_codes || unitOwners.value[idx].period_codes,
        commission_rate_percent:
          updated.commission_rate_percent ?? unitOwners.value[idx].commission_rate_percent,
      }
    }
    unitOwners.value = sortUnitOwners(unitOwners.value)
    await loadUnits()
    message.success(
      nextActive
        ? 'Лавка перенесена в продающие'
        : 'Лавка перенесена в лавки для требований',
    )
    assignmentsSubTab.value = nextActive ? 'selling' : 'requirements'
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось изменить статус лавки')
  } finally {
    togglingUnitId.value = null
  }
}


async function onDeleteUnit(row: AccountingUnitOwnerRow): Promise<void> {
  dialog.warning({
    title: 'Удалить лавку?',
    content: `Удалить «${shortLavkaName(row.name) || row.inn}» (ИНН ${row.inn}) из CRM? Если на лавке есть активные заявки — удаление будет запрещено.`,
    positiveText: 'Удалить',
    negativeText: 'Отмена',
    onPositiveClick: async () => {
      deletingUnitId.value = row.unit_id
      try {
        await deleteAccountingUnit(row.unit_id)
        unitOwners.value = unitOwners.value.filter((item) => item.unit_id !== row.unit_id)
        await loadUnits()
        message.success('Лавка удалена')
      } catch (err) {
        message.error(err instanceof AppError ? err.message : 'Не удалось удалить лавку')
        throw err
      } finally {
        deletingUnitId.value = null
      }
    },
  })
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
      title: 'Период',
      key: 'period_code',
      width: 180,
      render: (row) => renderOrderPeriodCell(row),
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
    title: 'Лавка',
    key: 'supplier',
    minWidth: 200,
    ellipsis: { tooltip: true },
    render: (row) => {
      const short = shortLavkaName(row.supplier.name) || row.supplier.inn
      const full = row.supplier.name || row.supplier.inn
      return h(
        'div',
        { class: 'accounting-page__deal-cell', title: full },
        [
          h('span', { class: 'accounting-page__deal-main accounting-page__lavka-short' }, short),
          h('span', { class: 'accounting-page__deal-sub' }, `ИНН ${row.supplier.inn}`),
        ],
      )
    },
  },
  {
    title: 'Получено',
    key: 'received_at',
    width: 112,
    render: (row) =>
      h('span', { class: 'accounting-page__mono' }, formatDocumentDate(row.received_at)),
  },
  {
    title: 'Срок',
    key: 'response_due_date',
    width: 110,
    render: (row) => {
      if (!row.response_due_date) return h('span', { class: 'accounting-page__deal-sub' }, '—')
      const cls = row.is_overdue
        ? 'accounting-page__due--overdue'
        : row.due_soon
          ? 'accounting-page__due--soon'
          : 'accounting-page__mono'
      return h('span', { class: cls }, formatDocumentDate(row.response_due_date))
    },
  },
  {
    title: 'Ответ',
    key: 'reply_status',
    width: 100,
    render: (row) => {
      const map: Record<string, { label: string; type: 'default' | 'success' | 'warning' | 'error' | 'info' }> = {
        none: { label: 'Нет', type: 'default' },
        sent: { label: 'Отправлен', type: 'info' },
        answered: { label: 'В СБИС', type: 'success' },
        error: { label: 'Ошибка', type: 'error' },
      }
      const status = row.reply_status || 'none'
      const meta = map[status] || { label: status, type: 'default' as const }
      return h(
        NTag,
        { size: 'small', bordered: false, type: meta.type, title: row.reply_error || undefined },
        { default: () => meta.label },
      )
    },
  },
  {
    title: 'Требование',
    key: 'title',
    minWidth: 140,
    ellipsis: { tooltip: true },
    render: (row) => {
      const title = row.title?.replace(/^Требование\s+/i, '') || 'ФНС'
      return h('span', { title: row.title }, title)
    },
  },
  {
    title: '',
    key: 'actions',
    width: 280,
    fixed: 'right',
    render: (row) => {
      const actions = []
      if (row.has_pdf) {
        actions.push(
          h(
            NButton,
            {
              size: 'tiny',
              quaternary: true,
              title: 'Просмотр PDF',
              loading: previewingReqId.value === row.id,
              onClick: () => openRequirementPreview(row),
            },
            { icon: () => h(Eye, { size: 14 }) },
          ),
          h(
            NButton,
            {
              size: 'tiny',
              quaternary: true,
              title: 'Скачать PDF',
              loading: downloadingReqId.value === row.id,
              onClick: () => onDownloadRequirement(row),
            },
            { icon: () => h(Download, { size: 14 }) },
          ),
        )
      }
      const replyDone = ['sent', 'answered'].includes(row.reply_status || 'none')
      if (!replyDone) {
        actions.push(
          h(
            NButton,
            {
              size: 'tiny',
              type: 'primary',
              secondary: true,
              onClick: () => openReplyModal(row),
            },
            { default: () => 'Ответ' },
          ),
        )
      }
      actions.push(
        h(
          NButton,
          {
            size: 'tiny',
            secondary: true,
            onClick: () => openTaskFromReqModal(row),
          },
          { default: () => 'Задача' },
        ),
      )
      if (row.status !== 'answered') {
        actions.push(
          h(
            NButton,
            {
              size: 'tiny',
              quaternary: true,
              title: 'Отметить прочитанным',
              loading: answeringReqId.value === row.id,
              onClick: () => onSetRequirementStatus(row, 'answered'),
            },
            { icon: () => h(MailOpen, { size: 14 }) },
          ),
        )
      } else {
        actions.push(
          h(
            NButton,
            {
              size: 'tiny',
              quaternary: true,
              title: 'Вернуть в непрочитанные',
              loading: answeringReqId.value === row.id,
              onClick: () => onSetRequirementStatus(row, 'new'),
            },
            { icon: () => h(Undo2, { size: 14 }) },
          ),
        )
      }
      return h('div', { class: 'accounting-page__req-actions' }, actions)
    },
  },
])

const requirementInnerColumns = computed<DataTableColumns<AccountingRequirement>>(() =>
  requirementColumns.value.filter((col) => 'key' in col && col.key !== 'supplier'),
)

watch(activeTab, async (tab) => {
  if (tab === 'orders') await loadOrders()
  else if (tab === 'requirements') await loadRequirements()
  else await loadUnitOwners()
})

watch([ordersPage, orderSupplierInn, orderPeriodCode], () => {
  if (activeTab.value === 'orders') void loadOrders()
})

watch(reqSupplierInn, () => {
  requirementsPage.value = 1
  if (activeTab.value === 'requirements') void loadRequirements()
})

watch(requirementsStatusTab, () => {
  const cached = peekCached<{ items: AccountingRequirement[]; total: number }>(
    requirementsCacheKey(),
  )
  if (cached) {
    requirements.value = cached.items
    requirementsTotal.value = cached.total
  } else {
    requirements.value = []
    requirementsTotal.value = 0
  }
  requirementsPage.value = 1
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
  const cachedOrders = peekCached<{ items: AccountingUnitOrderGroup[]; total: number }>(
    ORDERS_CACHE_KEY,
  )
  if (cachedOrders) {
    orderGroups.value = cachedOrders.items
    ordersTotal.value = cachedOrders.total
  }
  const cachedReqs = peekCached<{ items: AccountingRequirement[]; total: number }>(
    requirementsCacheKey(),
  )
  if (cachedReqs) {
    requirements.value = cachedReqs.items
    requirementsTotal.value = cachedReqs.total
  }
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
        <NButton :loading="anyLoading" @click="refreshAll">
          <template #icon>
            <RefreshCw :size="16" />
          </template>
          Обновить
        </NButton>
      </div>
    </header>

    <AppCard class="accounting-page__card">
      <NTabs v-model:value="activeTab" type="line" animated class="accounting-page__main-tabs">
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
              v-model:value="orderPeriodCode"
              :options="periodFilterOptions"
              clearable
              filterable
              placeholder="Период"
              style="min-width: 200px"
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
          <NSpin :show="ordersLoading && orderGroups.length === 0">
            <NEmpty v-if="!ordersLoading && orderGroups.length === 0" description="Нет заявок" />
            <NCollapse v-else v-model:expanded-names="expandedLavki">
              <NCollapseItem
                v-for="group in orderGroups"
                :key="group.unit.inn"
                :name="group.unit.inn"
              >
                <template #header>
                  <div class="accounting-page__lavka-header">
                    <div class="accounting-page__lavka-main">
                      <span class="accounting-page__lavka-title">{{ lavkaTitle(group.unit) }}</span>
                      <div class="accounting-page__lavka-meta">
                        <NTag size="small" :bordered="false">
                          {{ group.orders_count ?? group.orders.length }}
                          {{
                            (group.orders_count ?? group.orders.length) === 1
                              ? 'заявка'
                              : 'заявок'
                          }}
                        </NTag>
                        <NTag size="small" type="info" :bordered="false">
                          {{
                            formatAccountingMoney(
                              Number(group.orders_volume_sum ?? sumGroupVolume(group)),
                            )
                          }}
                        </NTag>
                        <NTag
                          v-if="group.unit.volume_limit != null"
                          size="small"
                          :type="
                            Number(group.orders_volume_sum ?? sumGroupVolume(group)) >
                            Number(group.unit.volume_limit)
                              ? 'error'
                              : 'warning'
                          "
                          :bordered="false"
                        >
                          лимит {{ formatAccountingMoney(Number(group.unit.volume_limit)) }}
                        </NTag>
                      </div>
                    </div>
                    <div v-if="isChief" class="accounting-page__lavka-actions">
                      <NButton
                        size="tiny"
                        secondary
                        type="primary"
                        class="accounting-page__rate-btn"
                        @click.stop="openEditRate(group.unit)"
                      >
                        {{ formatRateButtonLabel(group.unit.commission_rate_percent) }}
                      </NButton>
                      <NButton
                        size="tiny"
                        secondary
                        @click.stop="openEditLimit(group.unit)"
                      >
                        Лимит
                      </NButton>
                    </div>
                  </div>
                </template>
                <div class="accounting-page__orders-table">
                  <NDataTable
                    :columns="orderColumns()"
                    :data="group.orders"
                    :bordered="false"
                    :single-line="false"
                    :row-key="(row: AccountingUnitOrder) => row.order_id"
                    size="small"
                    :scroll-x="1180"
                  />
                </div>
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
          <div class="accounting-page__requirements">
            <NTabs v-model:value="requirementsStatusTab" type="segment" size="small" animated>
              <NTabPane name="new" tab="Непрочитанные" />
              <NTabPane name="answered" tab="Прочитанные" />
              <NTabPane name="replied" tab="Отвеченные" />
            </NTabs>
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
                title="Автосинхронизация — 2 раза в день; кнопка запускает фоновый забор"
                @click="onSyncRequirements"
              >
                <template #icon><RefreshCw :size="16" /></template>
                Забрать из СБИС сейчас
              </NButton>
            </div>
            <NSpin :show="requirementsLoading && requirements.length === 0">
              <NEmpty
                v-if="!requirementsLoading && requirements.length === 0"
                :description="
                  requirementsStatusTab === 'replied'
                    ? 'Нет отвеченных требований'
                    : requirementsStatusTab === 'answered'
                      ? 'Нет прочитанных требований'
                      : 'Нет непрочитанных требований'
                "
              />
              <NCollapse v-else v-model:expanded-names="expandedReqLavki">
                <NCollapseItem
                  v-for="group in requirementGroups"
                  :key="group.inn"
                  :name="group.inn"
                >
                  <template #header>
                    <div class="accounting-page__lavka-header">
                      <div class="accounting-page__lavka-main">
                        <span class="accounting-page__lavka-title">
                          {{ shortLavkaName(group.name) || group.name || group.inn }}
                        </span>
                        <div class="accounting-page__lavka-meta">
                          <NTag size="small" :bordered="false">
                            {{ group.items.length }}
                            {{ requirementCountLabel(group.items.length) }}
                          </NTag>
                          <NTag
                            v-if="group.items.some((row) => row.is_overdue)"
                            size="small"
                            type="error"
                            :bordered="false"
                          >
                            просрочено
                          </NTag>
                          <span class="accounting-page__deal-sub">ИНН {{ group.inn }}</span>
                        </div>
                      </div>
                    </div>
                  </template>
                  <div class="accounting-page__requirements-table">
                    <NDataTable
                      :columns="requirementInnerColumns"
                      :data="group.items"
                      :bordered="false"
                      :single-line="false"
                      :row-key="(row: AccountingRequirement) => row.id"
                      size="small"
                      :scroll-x="720"
                      :row-class-name="() => 'accounting-page__req-row'"
                    />
                  </div>
                </NCollapseItem>
              </NCollapse>
              <div
                v-if="requirementGroupsTotal > requirementsPageSize"
                class="accounting-page__pagination"
              >
                <NPagination
                  v-model:page="requirementsPage"
                  :page-size="requirementsPageSize"
                  :item-count="requirementGroupsTotal"
                />
              </div>
            </NSpin>
          </div>
        </NTabPane>

        <NTabPane v-if="isChief" name="assignments" tab="Назначения лавок">
          <NTabs v-model:value="assignmentsSubTab" type="segment" size="small" animated>
            <NTabPane name="selling" tab="Продающие лавки">
              <p class="accounting-page__owners-hint">
                Доступны для сдачи заявок. Назначенный бухгалтер видит заявки и требования по этим
                лавкам.
              </p>
              <NSpin :show="ownersLoading && sellingUnitOwners.length === 0">
                <NEmpty
                  v-if="!ownersLoading && sellingUnitOwners.length === 0"
                  description="Нет продающих лавок"
                />
                <div v-else class="accounting-page__owners">
                  <div
                    v-for="row in sellingUnitOwners"
                    :key="row.unit_id"
                    class="accounting-page__owner-row"
                    :class="{
                      'accounting-page__owner-row--unassigned': row.accountant_user_id == null,
                    }"
                  >
                    <div class="accounting-page__owner-lavka">
                      <span class="accounting-page__owner-name">{{
                        shortLavkaName(row.name) || row.name || row.inn
                      }}</span>
                      <span class="accounting-page__owner-inn">
                        {{ row.inn }} · {{ formatUnitRate(row.commission_rate_percent) }}
                      </span>
                      <span class="accounting-page__owner-periods">
                        {{ formatPeriodCodes(row.period_codes) }}
                      </span>
                    </div>
                    <div class="accounting-page__owner-actions">
                      <NButton size="small" secondary @click="openEditRate(row)">
                        <template #icon>
                          <Percent :size="14" />
                        </template>
                        Процент
                      </NButton>
                      <NButton size="small" secondary @click="openEditPeriods(row)">
                        <template #icon>
                          <CalendarRange :size="14" />
                        </template>
                        Периоды
                      </NButton>
                      <NButton
                        size="small"
                        quaternary
                        :loading="togglingUnitId === row.unit_id"
                        @click="onToggleUnitActive(row, false)"
                      >
                        В требования
                      </NButton>
                      <NButton
                        size="small"
                        quaternary
                        type="error"
                        :loading="deletingUnitId === row.unit_id"
                        @click="onDeleteUnit(row)"
                      >
                        Удалить
                      </NButton>
                    </div>
                    <NSelect
                      :value="row.accountant_user_id"
                      :options="accountantOptions"
                      clearable
                      filterable
                      placeholder="Бухгалтер"
                      :loading="savingUnitId === row.unit_id"
                      style="min-width: 220px"
                      @update:value="(value) => onAssignUnit(row, value as number | null)"
                    />
                  </div>
                </div>
              </NSpin>
            </NTabPane>
            <NTabPane name="requirements" tab="Лавки для требований">
              <p class="accounting-page__owners-hint">
                Не участвуют в сдаче. Назначенный бухгалтер видит только требования по этим лавкам.
              </p>
              <NSpin :show="ownersLoading && requirementUnitOwners.length === 0">
                <NEmpty
                  v-if="!ownersLoading && requirementUnitOwners.length === 0"
                  description="Нет лавок только для требований"
                />
                <div v-else class="accounting-page__owners">
                  <div
                    v-for="row in requirementUnitOwners"
                    :key="row.unit_id"
                    class="accounting-page__owner-row accounting-page__owner-row--requirements"
                    :class="{
                      'accounting-page__owner-row--unassigned': row.accountant_user_id == null,
                    }"
                  >
                    <div class="accounting-page__owner-lavka">
                      <span class="accounting-page__owner-name">{{
                        shortLavkaName(row.name) || row.name || row.inn
                      }}</span>
                      <span class="accounting-page__owner-inn">{{ row.inn }}</span>
                    </div>
                    <div class="accounting-page__owner-actions">
                      <NButton
                        size="small"
                        secondary
                        :loading="togglingUnitId === row.unit_id"
                        @click="onToggleUnitActive(row, true)"
                      >
                        В продающие
                      </NButton>
                      <NButton
                        size="small"
                        quaternary
                        type="error"
                        :loading="deletingUnitId === row.unit_id"
                        @click="onDeleteUnit(row)"
                      >
                        Удалить
                      </NButton>
                    </div>
                    <NSelect
                      :value="row.accountant_user_id"
                      :options="accountantOptions"
                      clearable
                      filterable
                      placeholder="Бухгалтер"
                      :loading="savingUnitId === row.unit_id"
                      style="min-width: 220px"
                      @update:value="(value) => onAssignUnit(row, value as number | null)"
                    />
                  </div>
                </div>
              </NSpin>
            </NTabPane>
          </NTabs>
        </NTabPane>
      </NTabs>
    </AppCard>

    <NModal
      v-model:show="replyModalOpen"
      preset="card"
      title="Ответ на требование в ФНС"
      style="width: 480px; max-width: 94vw"
    >
      <p v-if="replyTarget" class="accounting-page__owners-hint">
        Требование ФНС от
        {{ formatDate(replyTarget.received_at || replyTarget.created_at) }}
        по
        {{
          shortLavkaName(replyTarget.supplier.name) ||
          replyTarget.supplier.name ||
          replyTarget.supplier.inn
        }}
      </p>
      <p class="accounting-page__owners-hint">
        Загрузите комплект документов и отправьте.
      </p>
      <NUpload multiple :default-upload="false" @change="onReplyUploadChange">
        <NButton secondary>Выбрать файлы</NButton>
      </NUpload>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <NButton :loading="replySending" @click="submitReply(true)">Проверить</NButton>
          <NButton type="primary" :loading="replySending" @click="submitReply(false)">
            Отправить в ФНС
          </NButton>
        </div>
      </template>
    </NModal>

    <NModal
      v-model:show="taskModalOpen"
      preset="card"
      title="Поставить задачу по требованию"
      style="width: 480px; max-width: 94vw"
    >
      <NForm label-placement="top">
        <NFormItem label="Лавка (ООО)" required>
          <NSelect
            v-model:value="taskUnitInn"
            :options="taskUnitOptions"
            filterable
            placeholder="Выберите лавку"
          />
        </NFormItem>
        <NFormItem label="Исполнитель" required>
          <div style="display: flex; gap: 8px; width: 100%">
            <NSelect
              v-model:value="taskAssigneeId"
              :options="taskAssigneeOptions"
              filterable
              placeholder="Выберите исполнителя"
              style="flex: 1"
            />
            <NButton secondary @click="assignTaskToSelf">Себе</NButton>
          </div>
        </NFormItem>
        <NFormItem label="Заголовок" required>
          <NInput v-model:value="taskTitle" />
        </NFormItem>
        <NFormItem label="Текст">
          <NInput v-model:value="taskDescription" type="textarea" :autosize="{ minRows: 3 }" />
        </NFormItem>
        <NFormItem label="Крайний срок" required>
          <NDatePicker
            v-model:value="taskDueAt"
            type="datetime"
            clearable
            style="width: 100%"
          />
        </NFormItem>
        <NFormItem label="Файлы">
          <div class="accounting-page__task-files">
            <div
              v-if="taskTarget?.has_pdf"
              class="accounting-page__task-file-attached"
              :title="taskTarget.pdf_filename || 'Требование.pdf'"
            >
              <span class="accounting-page__task-file-name">
                {{ taskTarget.pdf_filename || 'Требование.pdf' }}
              </span>
              <NTag size="small" type="success" :bordered="false">прикреплено</NTag>
            </div>
            <NEmpty
              v-else
              description="У требования нет PDF"
              style="padding: 4px 0"
            />
            <NUpload multiple :default-upload="false" @change="onTaskUploadChange">
              <NButton secondary>Ещё файлы</NButton>
            </NUpload>
          </div>
        </NFormItem>
      </NForm>
      <template #footer>
        <NButton type="primary" :loading="taskSaving" @click="submitTaskFromReq">Создать</NButton>
      </template>
    </NModal>

    <AttachmentPreviewModal
      :open="previewOpen"
      :loading="previewLoading"
      :label="previewLabel"
      :blob-url="previewBlobUrl"
      :blob="previewBlob"
      :preview-kind="previewKind"
      @close="closePreview"
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
        <NFormItem label="Разрешённые периоды" required>
          <NSelect
            v-model:value="createForm.period_codes"
            :options="periodOptions"
            multiple
            filterable
            placeholder="Можно выбрать несколько"
            style="width: 100%"
          />
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

    <NModal
      v-model:show="rateEditOpen"
      preset="card"
      title="Процент по компании"
      style="width: 420px; max-width: 92vw"
    >
      <p class="accounting-page__rate-label">{{ rateEditLabel }}</p>
      <NFormItem label="Процент комиссии" :show-feedback="false">
        <NInputNumber
          v-model:value="rateEditValue"
          :min="0"
          :max="100"
          :precision="2"
          :step="0.1"
          style="width: 100%"
        >
          <template #suffix>%</template>
        </NInputNumber>
      </NFormItem>
      <p class="accounting-page__rate-hint">
        Новые заявки будут считаться с этим процентом. Уже созданные заказы не пересчитываются.
      </p>
      <template #footer>
        <div class="accounting-page__modal-actions">
          <NButton @click="rateEditOpen = false">Отмена</NButton>
          <NButton type="primary" :loading="rateEditSaving" @click="submitEditRate">
            Сохранить
          </NButton>
        </div>
      </template>
    </NModal>

    <NModal
      v-model:show="limitEditOpen"
      preset="card"
      title="Лимит объёма по лавке"
      style="width: 420px; max-width: 92vw"
    >
      <p class="accounting-page__rate-label">{{ limitEditLabel }}</p>
      <NFormItem label="Лимит объёма за период, ₽" :show-feedback="false">
        <NInputNumber
          v-model:value="limitEditValue"
          :min="0"
          :precision="2"
          :step="1000"
          clearable
          placeholder="Без лимита"
          style="width: 100%"
        />
      </NFormItem>
      <p class="accounting-page__rate-hint">
        Если сумма строк этой лавки в заявках периода (с учётом новой загрузки) превысит лимит —
        заявка не будет принята. Очистите поле, чтобы снять лимит.
      </p>
      <template #footer>
        <div class="accounting-page__modal-actions">
          <NButton @click="limitEditOpen = false">Отмена</NButton>
          <NButton type="primary" :loading="limitEditSaving" @click="submitEditLimit">
            Сохранить
          </NButton>
        </div>
      </template>
    </NModal>

    <NModal
      v-model:show="periodsEditOpen"
      preset="card"
      title="Периоды компании"
      style="width: 480px; max-width: 92vw"
    >
      <p class="accounting-page__rate-label">{{ periodsEditLabel }}</p>
      <NFormItem label="Разрешённые периоды" :show-feedback="false">
        <NSelect
          v-model:value="periodsEditValue"
          :options="periodOptions"
          multiple
          filterable
          placeholder="Можно выбрать несколько"
          style="width: 100%"
        />
      </NFormItem>
      <p class="accounting-page__rate-hint">
        Лавка будет доступна в ОПТ только для выбранных периодов сделки.
      </p>
      <template #footer>
        <div class="accounting-page__modal-actions">
          <NButton @click="periodsEditOpen = false">Отмена</NButton>
          <NButton type="primary" :loading="periodsEditSaving" @click="submitEditPeriods">
            Сохранить
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
  width: 100%;
  max-width: none;
}

.accounting-page__card {
  width: 100%;
}

.accounting-page__main-tabs :deep(.n-tabs-nav-scroll-content) {
  justify-content: center;
}

.accounting-page__main-tabs :deep(.n-tabs-nav) {
  width: 100%;
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

.accounting-page__requirements {
  width: 100%;
  max-width: none;
}

.accounting-page__requirements-table {
  width: 100%;
}

.accounting-page__requirements-table :deep(.n-data-table) {
  width: 100%;
}

.accounting-page__requirements-table :deep(.n-data-table-td) {
  vertical-align: middle;
  padding-top: 8px;
  padding-bottom: 8px;
}

.accounting-page__requirements-table :deep(.accounting-page__req-row td) {
  white-space: normal;
}

.accounting-page__lavka-short {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 260px;
}

.accounting-page__mono {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.accounting-page__req-actions {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 4px;
}

.accounting-page__requirements .accounting-page__filters {
  justify-content: flex-start;
}

.accounting-page__requirements .accounting-page__pagination {
  justify-content: center;
}

.accounting-page__due--overdue {
  color: #dc2626;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.accounting-page__due--soon {
  color: #d97706;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.accounting-page__period-label {
  cursor: pointer;
  text-decoration: underline dotted;
  text-underline-offset: 2px;
}

.accounting-page__pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.accounting-page__lavka-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-width: 0;
  flex-wrap: wrap;
  padding-right: 4px;
}

.accounting-page__lavka-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  flex: 1 1 240px;
}

.accounting-page__lavka-title {
  font-weight: 600;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.accounting-page__lavka-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.accounting-page__lavka-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.accounting-page__rate-btn {
  min-width: 3.25rem;
  font-variant-numeric: tabular-nums;
}

.accounting-page__orders-table {
  width: 100%;
  overflow-x: auto;
}

.accounting-page__orders-table :deep(.n-data-table-td) {
  vertical-align: top;
}

.accounting-page__rate-label {
  margin: 0 0 12px;
  font-weight: 600;
}

.accounting-page__rate-hint {
  margin: 8px 0 0;
  font-size: 0.85rem;
  color: var(--app-text-muted);
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

.accounting-page__owners-hint {
  margin: 0 0 12px;
  font-size: 0.85rem;
  color: var(--app-text-muted);
}

.accounting-page__task-files {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.accounting-page__task-file-attached {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--app-surface-elevated);
}

.accounting-page__task-file-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.875rem;
}

.accounting-page__owners {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.accounting-page__owner-row {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) auto minmax(220px, 280px);
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--app-surface-elevated);
}

.accounting-page__owner-row--unassigned {
  background: var(--app-warning-soft);
}

.accounting-page__owner-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
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

.accounting-page__owner-periods {
  font-size: 0.78rem;
  color: var(--app-text-muted);
}
</style>
