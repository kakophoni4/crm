<script setup lang="ts">
import type { UploadFileInfo } from 'naive-ui'
import {
  NButton,
  NCheckbox,
  NEmpty,
  NInput,
  NModal,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  NTooltip,
  NUpload,
  useMessage,
} from 'naive-ui'
import { ArrowLeft, Download, Eye, FileText, Folder, FolderOpen, FolderPlus, Send, Upload } from 'lucide-vue-next'
import { computed, onUnmounted, ref, watch } from 'vue'

import { uploadFile } from '@/features/chats/api'
import {
  createVaultFolder,
  downloadGroupFile,
  downloadStorageReceipt,
  downloadStorageSalesBook,
  listGroupFiles,
  listVaultFiles,
  uploadVaultFile,
  type GroupChatFile,
  type StorageReceiptItem,
  type StorageReceiptPeriodGroup,
  type StorageSalesBookItem,
  type StorageSalesBookUnitGroup,
  type VaultFile,
} from '@/features/storage/api'
import { fetchReceiptsTree, peekReceiptsTree } from '@/features/storage/receipts-tree-cache'
import { AppError } from '@/shared/api/http'
import {
  attachmentPreviewSupported,
  resolveAttachmentPreviewKind,
} from '@/shared/lib/attachment-preview-kind'
import { formatFileSize, maxUploadBytesFor, uploadLimitLabel } from '@/shared/config/uploads'
import { compareOptPeriodsDesc, formatOptPeriodLabel } from '@/features/leads/order-fields'
import AttachmentPreviewModal from '@/widgets/chat/AttachmentPreviewModal.vue'

const props = defineProps<{
  show: boolean
  chatId?: number | null
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  select: [file: { file_id: number; name: string; mime?: string }]
}>()

const message = useMessage()
const activeTab = ref<'vault' | 'dialog' | 'receipts'>('vault')
const loading = ref(false)
const vaultFiles = ref<VaultFile[]>([])
const vaultParentId = ref<number | null>(null)
const vaultPath = ref<{ id: number; name: string }[]>([])
const createFolderOpen = ref(false)
const createFolderName = ref('')
const createFolderLoading = ref(false)
const dialogFiles = ref<GroupChatFile[]>([])

const vaultFolderItems = computed(() => vaultFiles.value.filter((row) => row.is_folder))
const vaultFileItems = computed(() => vaultFiles.value.filter((row) => !row.is_folder))
const receiptPeriods = ref<StorageReceiptPeriodGroup[]>([])
const receiptPeriod = ref<string | null>(null)
/** null = type folders inside period */
const receiptFolder = ref<'main' | 'corrections' | 'sales_books' | null>(null)
/** ООО inside type folder */
const unitInn = ref<string | null>(null)
/** Buyer folder under sales-books lavka */
const buyerInn = ref<string | null>(null)
const busyId = ref<number | null>(null)
const selectedReceiptIds = ref<number[]>([])
const selectedSalesBookIds = ref<number[]>([])
const confirmingReceipts = ref(false)

function sortReceiptItems(items: StorageReceiptItem[]): StorageReceiptItem[] {
  return [...items].sort((a, b) => {
    const na = (a.supplier_name || a.supplier_inn || '').localeCompare(
      b.supplier_name || b.supplier_inn || '',
      'ru',
    )
    if (na !== 0) return na
    if (a.supplier_inn !== b.supplier_inn) return a.supplier_inn.localeCompare(b.supplier_inn)
    const ka = a.doc_kind === 'notice' ? 0 : 1
    const kb = b.doc_kind === 'notice' ? 0 : 1
    if (ka !== kb) return ka - kb
    return (a.source_filename || '').localeCompare(b.source_filename || '', 'ru')
  })
}

const previewOpen = ref(false)
const previewLoading = ref(false)
const previewName = ref('')
const previewMime = ref('')
const previewBlob = ref<Blob | null>(null)
const previewBlobUrl = ref<string | null>(null)

const previewKind = computed(() =>
  resolveAttachmentPreviewKind({
    name: previewName.value,
    mime: previewMime.value,
  }),
)

const hasChat = computed(() => props.chatId != null)

const selectedPeriodGroup = computed(() =>
  receiptPeriods.value.find((row) => row.period_code === receiptPeriod.value) ?? null,
)

const periodMainItems = computed(() =>
  sortReceiptItems((selectedPeriodGroup.value?.items ?? []).filter((row) => !row.is_correction)),
)

const periodCorrectionItems = computed(() =>
  sortReceiptItems((selectedPeriodGroup.value?.items ?? []).filter((row) => !!row.is_correction)),
)

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

const periodSalesBookUnits = computed((): StorageSalesBookUnitGroup[] => {
  const nested = selectedPeriodGroup.value?.sales_book_units ?? []
  if (nested.length) return nested
  const flat = selectedPeriodGroup.value?.sales_books ?? []
  const byInn = new Map<string, StorageSalesBookUnitGroup>()
  for (const item of flat) {
    let unit = byInn.get(item.seller_inn)
    if (!unit) {
      unit = {
        seller_inn: item.seller_inn,
        seller_name: shortLavkaName(item.seller_name) || item.seller_inn,
        orders: [{ order_id: 0, order_no: 0, lead_id: 0, buyer_inn: '', items: [] }],
      }
      byInn.set(item.seller_inn, unit)
    }
    unit.orders[0].items.push(item)
  }
  return [...byInn.values()].sort((a, b) => a.seller_name.localeCompare(b.seller_name, 'ru'))
})

const receiptUnitFolders = computed(() => {
  const items =
    receiptFolder.value === 'corrections' ? periodCorrectionItems.value : periodMainItems.value
  const byInn = new Map<string, { inn: string; name: string; items: StorageReceiptItem[] }>()
  for (const row of items) {
    let folder = byInn.get(row.supplier_inn)
    if (!folder) {
      folder = {
        inn: row.supplier_inn,
        name: shortLavkaName(row.supplier_name) || row.supplier_inn,
        items: [],
      }
      byInn.set(row.supplier_inn, folder)
    }
    folder.items.push(row)
  }
  return [...byInn.values()].sort((a, b) => a.name.localeCompare(b.name, 'ru'))
})

const selectedSalesUnit = computed((): StorageSalesBookUnitGroup | null => {
  if (!unitInn.value) return null
  return periodSalesBookUnits.value.find((u) => u.seller_inn === unitInn.value) ?? null
})

const periodSalesBuyerFolders = computed(() => {
  if (!selectedSalesUnit.value) return [] as { inn: string; name: string; items: StorageSalesBookItem[] }[]
  const byBuyer = new Map<string, { inn: string; name: string; items: StorageSalesBookItem[] }>()
  for (const item of selectedSalesUnit.value.orders.flatMap((o) => o.items)) {
    if (!item.buyer_inn) continue
    let folder = byBuyer.get(item.buyer_inn)
    if (!folder) {
      folder = {
        inn: item.buyer_inn,
        name: shortLavkaName(item.buyer_name) || item.buyer_name || item.buyer_inn,
        items: [],
      }
      byBuyer.set(item.buyer_inn, folder)
    } else if (item.buyer_name && folder.name === item.buyer_inn) {
      folder.name = shortLavkaName(item.buyer_name) || item.buyer_name
    }
    folder.items.push(item)
  }
  return [...byBuyer.values()].sort((a, b) => a.name.localeCompare(b.name, 'ru'))
})

const periodSalesBookItems = computed((): StorageSalesBookItem[] => {
  if (!buyerInn.value) return []
  return periodSalesBuyerFolders.value.find((f) => f.inn === buyerInn.value)?.items ?? []
})

const visibleReceiptItems = computed(() => {
  if (!unitInn.value) return []
  return receiptUnitFolders.value.find((u) => u.inn === unitInn.value)?.items ?? []
})

const receiptFolderLabel = computed(() => {
  if (receiptFolder.value === 'main') return 'Основные'
  if (receiptFolder.value === 'corrections') return 'Корректировки'
  if (receiptFolder.value === 'sales_books') return 'Книги продаж'
  return ''
})

const selectedReceiptCount = computed(() => selectedReceiptIds.value.length)
const selectedSalesBookCount = computed(() => selectedSalesBookIds.value.length)
const selectedAttachCount = computed(
  () => selectedReceiptCount.value + selectedSalesBookCount.value,
)

const allVisibleSelected = computed(() => {
  if (receiptFolder.value === 'sales_books') {
    const visible = periodSalesBookItems.value.filter((row) => row.has_pdf)
    if (!visible.length) return false
    return visible.every((row) => selectedSalesBookIds.value.includes(row.id))
  }
  const visible = visibleReceiptItems.value.filter((row) => row.has_pdf)
  if (!visible.length) return false
  return visible.every((row) => selectedReceiptIds.value.includes(row.id))
})

function isReceiptSelected(id: number): boolean {
  return selectedReceiptIds.value.includes(id)
}

function isSalesBookSelected(id: number): boolean {
  return selectedSalesBookIds.value.includes(id)
}

function toggleReceiptSelected(id: number, checked?: boolean): void {
  const on = checked ?? !isReceiptSelected(id)
  if (on) {
    if (!selectedReceiptIds.value.includes(id)) {
      selectedReceiptIds.value = [...selectedReceiptIds.value, id]
    }
  } else {
    selectedReceiptIds.value = selectedReceiptIds.value.filter((x) => x !== id)
  }
}

function toggleSalesBookSelected(id: number, checked?: boolean): void {
  const on = checked ?? !isSalesBookSelected(id)
  if (on) {
    if (!selectedSalesBookIds.value.includes(id)) {
      selectedSalesBookIds.value = [...selectedSalesBookIds.value, id]
    }
  } else {
    selectedSalesBookIds.value = selectedSalesBookIds.value.filter((x) => x !== id)
  }
}

function toggleSelectAllVisible(): void {
  if (receiptFolder.value === 'sales_books') {
    const visible = periodSalesBookItems.value.filter((row) => row.has_pdf)
    if (allVisibleSelected.value) {
      const drop = new Set(visible.map((row) => row.id))
      selectedSalesBookIds.value = selectedSalesBookIds.value.filter((id) => !drop.has(id))
      return
    }
    const merged = new Set(selectedSalesBookIds.value)
    for (const row of visible) merged.add(row.id)
    selectedSalesBookIds.value = [...merged]
    return
  }
  const visible = visibleReceiptItems.value.filter((row) => row.has_pdf)
  if (allVisibleSelected.value) {
    const drop = new Set(visible.map((row) => row.id))
    selectedReceiptIds.value = selectedReceiptIds.value.filter((id) => !drop.has(id))
    return
  }
  const merged = new Set(selectedReceiptIds.value)
  for (const row of visible) merged.add(row.id)
  selectedReceiptIds.value = [...merged]
}

function findReceiptById(id: number): StorageReceiptItem | null {
  for (const period of receiptPeriods.value) {
    const hit = period.items.find((row) => row.id === id)
    if (hit) return hit
  }
  return null
}

function findSalesBookById(id: number): StorageSalesBookItem | null {
  for (const period of receiptPeriods.value) {
    for (const unit of period.sales_book_units ?? []) {
      for (const order of unit.orders) {
        const hit = order.items.find((row) => row.id === id)
        if (hit) return hit
      }
    }
    const hit = (period.sales_books ?? []).find((row) => row.id === id)
    if (hit) return hit
  }
  return null
}

async function loadVault(): Promise<void> {
  loading.value = true
  try {
    const data = await listVaultFiles({
      parent_id: vaultParentId.value,
      limit: 100,
    })
    vaultFiles.value = data.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить хранилище')
  } finally {
    loading.value = false
  }
}

function openVaultFolder(folder: VaultFile): void {
  vaultPath.value = [...vaultPath.value, { id: folder.id, name: folder.original_name }]
  vaultParentId.value = folder.id
  vaultFiles.value = []
  void loadVault()
}

function vaultBack(): void {
  if (!vaultPath.value.length) return
  const next = vaultPath.value.slice(0, -1)
  vaultPath.value = next
  vaultParentId.value = next.length ? next[next.length - 1].id : null
  vaultFiles.value = []
  void loadVault()
}

function goVaultPath(index: number): void {
  if (index < 0) {
    vaultPath.value = []
    vaultParentId.value = null
  } else {
    vaultPath.value = vaultPath.value.slice(0, index + 1)
    vaultParentId.value = vaultPath.value[index]?.id ?? null
  }
  vaultFiles.value = []
  void loadVault()
}

function openCreateFolder(): void {
  createFolderName.value = ''
  createFolderOpen.value = true
}

async function submitCreateFolder(): Promise<void> {
  const name = createFolderName.value.trim()
  if (!name) {
    message.warning('Укажите имя папки')
    return
  }
  createFolderLoading.value = true
  try {
    await createVaultFolder({ name, parent_id: vaultParentId.value })
    message.success('Папка создана')
    createFolderOpen.value = false
    await loadVault()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось создать папку')
  } finally {
    createFolderLoading.value = false
  }
}

const vaultUploadQueue: File[] = []
let vaultUploadFlushTimer: ReturnType<typeof setTimeout> | null = null
const vaultUploading = ref(false)

async function onVaultUpload(data: { file: UploadFileInfo }): Promise<boolean> {
  const file = data.file.file
  if (!file) return false
  vaultUploadQueue.push(file)
  if (vaultUploadFlushTimer) clearTimeout(vaultUploadFlushTimer)
  vaultUploadFlushTimer = setTimeout(() => {
    void flushVaultUploads()
  }, 40)
  return false
}

async function flushVaultUploads(): Promise<void> {
  if (vaultUploading.value) return
  const files = vaultUploadQueue.splice(0)
  if (!files.length) return
  vaultUploading.value = true
  let ok = 0
  try {
    for (const file of files) {
      if (file.size > maxUploadBytesFor(file)) {
        message.error(`${file.name}: слишком большой (макс. ${uploadLimitLabel(file)})`)
        continue
      }
      try {
        await uploadVaultFile(file, { parent_id: vaultParentId.value })
        ok += 1
      } catch (err) {
        message.error(
          err instanceof AppError ? `${file.name}: ${err.message}` : `${file.name}: ошибка загрузки`,
        )
      }
    }
    if (ok === 1) message.success('Файл добавлен в хранилище')
    else if (ok > 1) message.success(`Загружено файлов: ${ok}`)
    if (ok > 0) await loadVault()
  } finally {
    vaultUploading.value = false
    if (vaultUploadQueue.length) void flushVaultUploads()
  }
}

async function loadDialog(): Promise<void> {
  if (props.chatId == null) {
    dialogFiles.value = []
    return
  }
  loading.value = true
  try {
    const data = await listGroupFiles({ chat_id: props.chatId, limit: 100 })
    dialogFiles.value = data.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить файлы диалога')
  } finally {
    loading.value = false
  }
}

async function loadReceipts(): Promise<void> {
  const cached = peekReceiptsTree()
  if (cached?.length) {
    receiptPeriods.value = [...cached].sort((a, b) =>
      compareOptPeriodsDesc(a.period_code, b.period_code),
    )
  }
  if (!receiptPeriods.value.length) loading.value = true
  try {
    const data = await fetchReceiptsTree()
    receiptPeriods.value = [...data.periods].sort((a, b) =>
      compareOptPeriodsDesc(a.period_code, b.period_code),
    )
    if (
      receiptPeriod.value &&
      !data.periods.some((row) => row.period_code === receiptPeriod.value)
    ) {
      receiptPeriod.value = null
      receiptFolder.value = null
      unitInn.value = null
      buyerInn.value = null
    }
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить квитанции')
  } finally {
    loading.value = false
  }
}

async function loadActive(): Promise<void> {
  if (activeTab.value === 'dialog') await loadDialog()
  else if (activeTab.value === 'receipts') await loadReceipts()
  else await loadVault()
}

watch(
  () => props.show,
  (open) => {
    if (!open) return
    activeTab.value = 'vault'
    vaultParentId.value = null
    vaultPath.value = []
    receiptPeriod.value = null
    receiptFolder.value = null
    unitInn.value = null
    buyerInn.value = null
    selectedReceiptIds.value = []
    selectedSalesBookIds.value = []
    void loadActive()
  },
)

watch(activeTab, () => {
  if (props.show) void loadActive()
})

function onShowUpdate(value: boolean): void {
  emit('update:show', value)
}

function pickVault(file: VaultFile): void {
  if (file.is_folder || file.file_id == null) {
    openVaultFolder(file)
    return
  }
  emit('select', {
    file_id: file.file_id,
    name: file.original_name,
    mime: file.mime_type,
  })
  emit('update:show', false)
}

function pickDialog(file: GroupChatFile): void {
  if (file.file_id == null) {
    message.warning('Файл ещё не готов к повторной отправке')
    return
  }
  emit('select', {
    file_id: file.file_id,
    name: file.original_name,
    mime: file.mime_type,
  })
  emit('update:show', false)
}

function senderLabel(file: GroupChatFile): string {
  return file.sender_display_name?.trim() || (file.direction === 'inbound' ? 'Клиент' : 'Оператор')
}

function canPreview(name: string, mime: string): boolean {
  return attachmentPreviewSupported(resolveAttachmentPreviewKind({ name, mime }))
}

function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function resetPreview(): void {
  if (previewBlobUrl.value) URL.revokeObjectURL(previewBlobUrl.value)
  previewBlobUrl.value = null
  previewBlob.value = null
}

async function openPreview(name: string, mime: string, load: () => Promise<Blob>): Promise<void> {
  if (!canPreview(name, mime)) {
    message.warning('Предпросмотр для этого типа файла недоступен')
    return
  }
  resetPreview()
  previewName.value = name
  previewMime.value = mime || ''
  previewOpen.value = true
  previewLoading.value = true
  try {
    const blob = await load()
    previewBlob.value = blob
    previewBlobUrl.value = URL.createObjectURL(blob)
  } catch (err) {
    previewOpen.value = false
    message.error(err instanceof AppError ? err.message : 'Не удалось открыть файл')
  } finally {
    previewLoading.value = false
  }
}

function closePreview(): void {
  previewOpen.value = false
  resetPreview()
}

async function onDownloadDialog(file: GroupChatFile): Promise<void> {
  busyId.value = file.id
  try {
    const blob = await downloadGroupFile(file.id)
    saveBlob(blob, file.original_name)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать файл')
  } finally {
    busyId.value = null
  }
}

async function onPreviewDialog(file: GroupChatFile): Promise<void> {
  busyId.value = file.id
  await openPreview(file.original_name, file.mime_type || '', () => downloadGroupFile(file.id))
  busyId.value = null
}

async function onAddToVault(file: GroupChatFile): Promise<void> {
  busyId.value = file.id
  try {
    const blob = await downloadGroupFile(file.id)
    const uploaded = new File([blob], file.original_name, {
      type: file.mime_type || blob.type || 'application/octet-stream',
    })
    await uploadVaultFile(uploaded, { parent_id: null })
    message.success(`«${file.original_name}» добавлен в Мои файлы`)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось добавить в Мои файлы')
  } finally {
    busyId.value = null
  }
}

function receiptKindLabel(row: StorageReceiptItem): string {
  const base = row.doc_kind === 'notice' ? 'Извещение' : 'Квитанция'
  return row.is_correction ? `${base} · корректировка` : base
}

function openPeriod(code: string): void {
  receiptPeriod.value = code
  receiptFolder.value = null
  unitInn.value = null
  buyerInn.value = null
}

function openReceiptTypeFolder(kind: 'main' | 'corrections' | 'sales_books'): void {
  receiptFolder.value = kind
  unitInn.value = null
  buyerInn.value = null
}

function openUnit(inn: string): void {
  unitInn.value = inn
  buyerInn.value = null
}

function openBuyer(inn: string): void {
  buyerInn.value = inn
}

function receiptsBack(): void {
  if (buyerInn.value) {
    buyerInn.value = null
    return
  }
  if (unitInn.value) {
    unitInn.value = null
    return
  }
  if (receiptFolder.value) {
    receiptFolder.value = null
    return
  }
  receiptPeriod.value = null
}

async function onPreviewReceipt(row: StorageReceiptItem): Promise<void> {
  if (!row.has_pdf) {
    message.warning('PDF недоступен')
    return
  }
  busyId.value = row.id
  const name = row.source_filename || `receipt-${row.id}.pdf`
  await openPreview(name, 'application/pdf', () => downloadStorageReceipt(row.id))
  busyId.value = null
}

async function onDownloadReceipt(row: StorageReceiptItem): Promise<void> {
  if (!row.has_pdf) return
  busyId.value = row.id
  try {
    const blob = await downloadStorageReceipt(row.id)
    saveBlob(blob, row.source_filename || `receipt-${row.id}.pdf`)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать квитанцию')
  } finally {
    busyId.value = null
  }
}

async function onPreviewSalesBook(row: StorageSalesBookItem): Promise<void> {
  if (!row.has_pdf) {
    message.warning('PDF недоступен')
    return
  }
  busyId.value = row.id
  const name = row.source_filename || `sales-book-${row.id}.pdf`
  await openPreview(name, 'application/pdf', () => downloadStorageSalesBook(row.id))
  busyId.value = null
}

async function onDownloadSalesBook(row: StorageSalesBookItem): Promise<void> {
  if (!row.has_pdf) return
  busyId.value = row.id
  try {
    const blob = await downloadStorageSalesBook(row.id)
    saveBlob(blob, row.source_filename || `sales-book-${row.id}.pdf`)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать книгу продаж')
  } finally {
    busyId.value = null
  }
}

async function confirmSelectedReceipts(): Promise<void> {
  const receiptIds = [...selectedReceiptIds.value]
  const salesIds = [...selectedSalesBookIds.value]
  if (!receiptIds.length && !salesIds.length) {
    message.warning('Выбери хотя бы один файл')
    return
  }
  confirmingReceipts.value = true
  let ok = 0
  try {
    for (const id of receiptIds) {
      const row = findReceiptById(id)
      if (!row?.has_pdf) continue
      try {
        const blob = await downloadStorageReceipt(row.id)
        const name = row.source_filename || `receipt-${row.id}.pdf`
        const file = new File([blob], name, { type: 'application/pdf' })
        const uploaded = await uploadFile(file)
        emit('select', {
          file_id: uploaded.id,
          name: uploaded.name || name,
          mime: uploaded.mime || 'application/pdf',
        })
        ok += 1
      } catch (err) {
        message.error(
          err instanceof AppError
            ? err.message
            : `Не удалось добавить «${row.source_filename}»`,
        )
      }
    }
    for (const id of salesIds) {
      const row = findSalesBookById(id)
      if (!row?.has_pdf) continue
      try {
        const blob = await downloadStorageSalesBook(row.id)
        const name = row.source_filename || `sales-book-${row.id}.pdf`
        const file = new File([blob], name, { type: 'application/pdf' })
        const uploaded = await uploadFile(file)
        emit('select', {
          file_id: uploaded.id,
          name: uploaded.name || name,
          mime: uploaded.mime || 'application/pdf',
        })
        ok += 1
      } catch (err) {
        message.error(
          err instanceof AppError
            ? err.message
            : `Не удалось добавить «${row.source_filename}»`,
        )
      }
    }
    if (ok > 0) {
      message.success(ok === 1 ? 'Файл добавлен в сообщение' : `Добавлено файлов: ${ok}`)
      selectedReceiptIds.value = []
      selectedSalesBookIds.value = []
      emit('update:show', false)
    }
  } finally {
    confirmingReceipts.value = false
  }
}

function clearAttachSelection(): void {
  selectedReceiptIds.value = []
  selectedSalesBookIds.value = []
}

onUnmounted(() => {
  resetPreview()
})
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    title="Файлы"
    style="width: min(640px, 96vw)"
    @update:show="onShowUpdate"
  >
    <NTabs v-model:value="activeTab" type="line" size="small">
      <NTabPane name="vault" tab="Хранилище" />
      <NTabPane name="dialog" tab="Текущий диалог" :disabled="!hasChat" />
      <NTabPane name="receipts" tab="Квитанции" />
    </NTabs>

    <NSpin :show="loading">
      <template v-if="activeTab === 'vault'">
        <div v-if="vaultPath.length" class="explorer-nav">
          <NButton size="tiny" quaternary @click="vaultBack">
            <template #icon><ArrowLeft :size="14" /></template>
            Назад
          </NButton>
          <div class="explorer-path">
            <button type="button" class="explorer-crumb" @click="goVaultPath(-1)">
              Мои файлы
            </button>
            <template v-for="(crumb, idx) in vaultPath" :key="crumb.id">
              <span class="explorer-sep">/</span>
              <button
                type="button"
                class="explorer-crumb"
                :class="{ 'explorer-crumb--current': idx === vaultPath.length - 1 }"
                @click="goVaultPath(idx)"
              >
                {{ crumb.name }}
              </button>
            </template>
          </div>
        </div>
        <div class="vault-toolbar">
          <NButton size="small" secondary @click="openCreateFolder">
            <template #icon><FolderPlus :size="14" /></template>
            Создать папку
          </NButton>
          <NUpload multiple :show-file-list="false" @before-upload="onVaultUpload">
            <NButton size="small" type="primary" :loading="vaultUploading">
              <template #icon><Upload :size="14" /></template>
              Загрузить
            </NButton>
          </NUpload>
        </div>
        <NEmpty
          v-if="!vaultFolderItems.length && !vaultFileItems.length && !loading"
          description="В этой папке пусто"
        />
        <ul v-if="vaultFolderItems.length" class="explorer-list">
          <li
            v-for="folder in vaultFolderItems"
            :key="folder.id"
            class="explorer-item"
            @click="openVaultFolder(folder)"
          >
            <Folder :size="16" class="explorer-icon" />
            <span class="file-name">{{ folder.original_name }}</span>
          </li>
        </ul>
        <ul v-if="vaultFileItems.length" class="file-list">
          <li v-for="file in vaultFileItems" :key="file.id" class="file-item">
            <div class="file-info">
              <FolderOpen :size="16" class="file-icon" />
              <div>
                <div class="file-name">{{ file.original_name }}</div>
                <div class="file-meta">{{ formatFileSize(file.size_bytes) }}</div>
              </div>
            </div>
            <NButton size="small" type="primary" @click="pickVault(file)">Выбрать</NButton>
          </li>
        </ul>
      </template>

      <template v-else-if="activeTab === 'dialog'">
        <NEmpty
          v-if="!hasChat"
          description="Откройте чат, чтобы видеть файлы переписки"
        />
        <NEmpty
          v-else-if="!dialogFiles.length && !loading"
          description="В этом диалоге ещё нет файлов"
        />
        <ul v-else class="file-list">
          <li v-for="file in dialogFiles" :key="file.id" class="file-item">
            <div class="file-info">
              <FolderOpen :size="16" class="file-icon" />
              <div>
                <div class="file-name">{{ file.original_name }}</div>
                <div class="file-meta">
                  {{ formatFileSize(file.size_bytes) }} ·
                  {{ new Date(file.created_at).toLocaleString('ru-RU') }}
                </div>
              </div>
            </div>
            <div class="file-actions">
              <NTag size="tiny" :bordered="false">{{ senderLabel(file) }}</NTag>
              <NTooltip>
                <template #trigger>
                  <NButton
                    size="tiny"
                    quaternary
                    :disabled="!canPreview(file.original_name, file.mime_type)"
                    @click="onPreviewDialog(file)"
                  >
                    <template #icon><Eye :size="14" /></template>
                  </NButton>
                </template>
                Предпросмотр
              </NTooltip>
              <NTooltip>
                <template #trigger>
                  <NButton
                    size="tiny"
                    quaternary
                    :loading="busyId === file.id"
                    @click="onDownloadDialog(file)"
                  >
                    <template #icon><Download :size="14" /></template>
                  </NButton>
                </template>
                Скачать
              </NTooltip>
              <NTooltip>
                <template #trigger>
                  <NButton
                    size="tiny"
                    quaternary
                    :loading="busyId === file.id"
                    @click="onAddToVault(file)"
                  >
                    <template #icon><FolderPlus :size="14" /></template>
                  </NButton>
                </template>
                В Мои файлы
              </NTooltip>
              <NButton
                size="small"
                type="primary"
                :disabled="file.file_id == null"
                @click="pickDialog(file)"
              >
                <template #icon><Send :size="14" /></template>
                Отправить
              </NButton>
            </div>
          </li>
        </ul>
      </template>

      <template v-else>
        <div v-if="receiptPeriod" class="receipts-nav">
          <NButton size="tiny" quaternary @click="receiptsBack">
            <template #icon><ArrowLeft :size="14" /></template>
            Назад
          </NButton>
          <span class="receipts-nav-path">
            {{ formatOptPeriodLabel(receiptPeriod) || receiptPeriod }}
            <template v-if="receiptFolder"> / {{ receiptFolderLabel }}</template>
            <template v-if="unitInn && receiptFolder === 'sales_books' && selectedSalesUnit">
              / {{ shortLavkaName(selectedSalesUnit.seller_name) || selectedSalesUnit.seller_name }}
            </template>
            <template v-else-if="unitInn">
              / {{ receiptUnitFolders.find((u) => u.inn === unitInn)?.name || unitInn }}
            </template>
            <template v-if="buyerInn">
              /
              {{
                periodSalesBuyerFolders.find((f) => f.inn === buyerInn)?.name || buyerInn
              }}
            </template>
          </span>
        </div>

        <NEmpty
          v-if="!receiptPeriods.length && !loading"
          description="Квитанций и книг продаж пока нет"
        />

        <!-- Period folders -->
        <ul v-else-if="!receiptPeriod" class="file-list">
          <li
            v-for="period in receiptPeriods"
            :key="period.period_code"
            class="file-item file-item--folder"
            @click="openPeriod(period.period_code)"
          >
            <div class="file-info">
              <FolderOpen :size="16" class="file-icon" />
              <div>
                <div class="file-name">
                  {{ formatOptPeriodLabel(period.period_code) || period.period_code }}
                </div>
              </div>
            </div>
            <NButton size="small" secondary @click.stop="openPeriod(period.period_code)">
              Открыть
            </NButton>
          </li>
        </ul>

        <!-- Type folders: Основные / Корректировки / Книги продаж -->
        <ul v-else-if="!receiptFolder" class="file-list">
          <li
            v-if="periodMainItems.length"
            class="file-item file-item--folder"
            @click="openReceiptTypeFolder('main')"
          >
            <div class="file-info">
              <FolderOpen :size="16" class="file-icon" />
              <div class="file-name">Основные</div>
            </div>
            <NButton size="small" secondary @click.stop="openReceiptTypeFolder('main')">
              Открыть
            </NButton>
          </li>
          <li
            v-if="periodCorrectionItems.length"
            class="file-item file-item--folder"
            @click="openReceiptTypeFolder('corrections')"
          >
            <div class="file-info">
              <FolderOpen :size="16" class="file-icon" />
              <div class="file-name">Корректировки</div>
            </div>
            <NButton size="small" secondary @click.stop="openReceiptTypeFolder('corrections')">
              Открыть
            </NButton>
          </li>
          <li
            v-if="periodSalesBookUnits.length"
            class="file-item file-item--folder"
            @click="openReceiptTypeFolder('sales_books')"
          >
            <div class="file-info">
              <FolderOpen :size="16" class="file-icon" />
              <div class="file-name">Книги продаж</div>
            </div>
            <NButton size="small" secondary @click.stop="openReceiptTypeFolder('sales_books')">
              Открыть
            </NButton>
          </li>
          <NEmpty
            v-if="
              !periodMainItems.length &&
              !periodCorrectionItems.length &&
              !periodSalesBookUnits.length &&
              !loading
            "
            description="В этом периоде пусто"
          />
        </ul>

        <!-- ООО under Основные / Корректировки -->
        <ul
          v-else-if="
            !unitInn && (receiptFolder === 'main' || receiptFolder === 'corrections')
          "
          class="file-list"
        >
          <li
            v-for="unit in receiptUnitFolders"
            :key="unit.inn"
            class="file-item file-item--folder"
            @click="openUnit(unit.inn)"
          >
            <div class="file-info">
              <FolderOpen :size="16" class="file-icon" />
              <div class="file-name">{{ unit.name }}</div>
            </div>
            <NButton size="small" secondary @click.stop="openUnit(unit.inn)">Открыть</NButton>
          </li>
          <NEmpty v-if="!receiptUnitFolders.length && !loading" description="Папок нет" />
        </ul>

        <!-- ООО under Книги продаж -->
        <ul
          v-else-if="!unitInn && receiptFolder === 'sales_books'"
          class="file-list"
        >
          <li
            v-for="unit in periodSalesBookUnits"
            :key="unit.seller_inn"
            class="file-item file-item--folder"
            @click="openUnit(unit.seller_inn)"
          >
            <div class="file-info">
              <FolderOpen :size="16" class="file-icon" />
              <div class="file-name">
                {{ shortLavkaName(unit.seller_name) || unit.seller_name }}
              </div>
            </div>
            <NButton size="small" secondary @click.stop="openUnit(unit.seller_inn)">
              Открыть
            </NButton>
          </li>
          <NEmpty v-if="!periodSalesBookUnits.length && !loading" description="Книг продаж нет" />
        </ul>

        <!-- Files: receipts -->
        <template
          v-else-if="unitInn && (receiptFolder === 'main' || receiptFolder === 'corrections')"
        >
          <div v-if="visibleReceiptItems.length" class="receipts-toolbar">
            <NCheckbox
              :checked="allVisibleSelected"
              :disabled="!visibleReceiptItems.some((r) => r.has_pdf)"
              @update:checked="toggleSelectAllVisible"
            >
              Выбрать все на экране
            </NCheckbox>
          </div>
          <ul class="file-list">
            <li
              v-for="row in visibleReceiptItems"
              :key="row.id"
              class="file-item"
              :class="{ 'file-item--selected': isReceiptSelected(row.id) }"
              @click="row.has_pdf && toggleReceiptSelected(row.id)"
            >
              <div class="file-info" @click.stop>
                <NCheckbox
                  :checked="isReceiptSelected(row.id)"
                  :disabled="!row.has_pdf"
                  @update:checked="(v) => toggleReceiptSelected(row.id, v)"
                />
                <FileText :size="16" class="file-icon" />
                <div>
                  <div class="file-name">{{ row.source_filename }}</div>
                  <div class="file-meta">{{ receiptKindLabel(row) }}</div>
                </div>
              </div>
              <div class="file-actions" @click.stop>
                <NTooltip>
                  <template #trigger>
                    <NButton
                      size="tiny"
                      quaternary
                      :disabled="!row.has_pdf"
                      :loading="busyId === row.id"
                      @click="onPreviewReceipt(row)"
                    >
                      <template #icon><Eye :size="14" /></template>
                    </NButton>
                  </template>
                  Открыть
                </NTooltip>
                <NTooltip>
                  <template #trigger>
                    <NButton
                      size="tiny"
                      quaternary
                      :disabled="!row.has_pdf"
                      :loading="busyId === row.id"
                      @click="onDownloadReceipt(row)"
                    >
                      <template #icon><Download :size="14" /></template>
                    </NButton>
                  </template>
                  Скачать
                </NTooltip>
              </div>
            </li>
          </ul>
          <NEmpty v-if="!visibleReceiptItems.length && !loading" description="Файлов нет" />
        </template>

        <!-- Buyer folders under lavka (sales books) -->
        <ul
          v-else-if="unitInn && !buyerInn && receiptFolder === 'sales_books'"
          class="file-list"
        >
          <li
            v-for="buyer in periodSalesBuyerFolders"
            :key="buyer.inn"
            class="file-item file-item--folder"
            @click="openBuyer(buyer.inn)"
          >
            <div class="file-info">
              <FolderOpen :size="16" class="file-icon" />
              <div class="file-name">{{ buyer.name }}</div>
            </div>
            <NButton size="small" secondary @click.stop="openBuyer(buyer.inn)">Открыть</NButton>
          </li>
          <NEmpty
            v-if="!periodSalesBuyerFolders.length && !loading"
            description="Покупателей нет"
          />
        </ul>

        <!-- Files: sales books inside buyer folder -->
        <template v-else-if="unitInn && buyerInn && receiptFolder === 'sales_books'">
          <div v-if="periodSalesBookItems.length" class="receipts-toolbar">
            <NCheckbox
              :checked="allVisibleSelected"
              :disabled="!periodSalesBookItems.some((r) => r.has_pdf)"
              @update:checked="toggleSelectAllVisible"
            >
              Выбрать все на экране
            </NCheckbox>
          </div>
          <ul v-if="periodSalesBookItems.length" class="file-list">
            <li
              v-for="row in periodSalesBookItems"
              :key="`sb-${row.id}`"
              class="file-item"
              :class="{ 'file-item--selected': isSalesBookSelected(row.id) }"
              @click="row.has_pdf && toggleSalesBookSelected(row.id)"
            >
              <div class="file-info" @click.stop>
                <NCheckbox
                  :checked="isSalesBookSelected(row.id)"
                  :disabled="!row.has_pdf"
                  @update:checked="(v) => toggleSalesBookSelected(row.id, v)"
                />
                <FileText :size="16" class="file-icon" />
                <div>
                  <div class="file-name">{{ row.source_filename }}</div>
                  <div class="file-meta">ИНН {{ row.buyer_inn }}</div>
                </div>
              </div>
              <div class="file-actions" @click.stop>
                <NTooltip>
                  <template #trigger>
                    <NButton
                      size="tiny"
                      quaternary
                      :disabled="!row.has_pdf"
                      :loading="busyId === row.id"
                      @click="onPreviewSalesBook(row)"
                    >
                      <template #icon><Eye :size="14" /></template>
                    </NButton>
                  </template>
                  Открыть
                </NTooltip>
                <NTooltip>
                  <template #trigger>
                    <NButton
                      size="tiny"
                      quaternary
                      :disabled="!row.has_pdf"
                      :loading="busyId === row.id"
                      @click="onDownloadSalesBook(row)"
                    >
                      <template #icon><Download :size="14" /></template>
                    </NButton>
                  </template>
                  Скачать
                </NTooltip>
              </div>
            </li>
          </ul>
          <NEmpty v-else-if="!loading" description="Книг продаж нет" />
        </template>
      </template>
    </NSpin>

    <div v-if="activeTab === 'receipts' && selectedAttachCount" class="receipts-footer">
      <span>Выбрано: {{ selectedAttachCount }}</span>
      <div class="receipts-footer-actions">
        <NButton quaternary :disabled="confirmingReceipts" @click="clearAttachSelection">
          Сбросить
        </NButton>
        <NButton
          type="primary"
          :loading="confirmingReceipts"
          @click="confirmSelectedReceipts"
        >
          <template #icon><Send :size="14" /></template>
          Добавить в сообщение
        </NButton>
      </div>
    </div>

    <AttachmentPreviewModal
      :open="previewOpen"
      :loading="previewLoading"
      :label="previewName"
      :blob-url="previewBlobUrl"
      :blob="previewBlob"
      :preview-kind="previewKind"
      @close="closePreview"
    />
  </NModal>

  <NModal
    v-model:show="createFolderOpen"
    preset="card"
    title="Новая папка"
    style="width: 360px; max-width: 94vw"
  >
    <NInput
      v-model:value="createFolderName"
      placeholder="Название папки"
      @keyup.enter="submitCreateFolder"
    />
    <template #footer>
      <NButton type="primary" :loading="createFolderLoading" @click="submitCreateFolder">
        Создать
      </NButton>
    </template>
  </NModal>
</template>

<style scoped>
.vault-toolbar {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.explorer-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.explorer-path {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  font-size: 0.85rem;
  min-width: 0;
}

.explorer-crumb {
  border: 0;
  background: transparent;
  color: var(--app-accent);
  cursor: pointer;
  padding: 0;
  font: inherit;
}

.explorer-crumb--current {
  color: var(--app-text);
  cursor: default;
  font-weight: 600;
}

.explorer-sep {
  color: var(--app-text-muted);
}

.explorer-list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  border: 1px solid var(--app-border, var(--n-border-color));
  border-radius: 8px;
  overflow: hidden;
}

.explorer-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid color-mix(in srgb, var(--app-border, #ddd) 70%, transparent);
}

.explorer-item:last-child {
  border-bottom: 0;
}

.explorer-item:hover {
  background: color-mix(in srgb, var(--app-accent, #18a058) 8%, transparent);
}

.explorer-icon {
  flex-shrink: 0;
  color: #ca8a04;
}

.file-list {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  max-height: 400px;
  overflow-y: auto;
}

.file-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--n-border-color);
}

.file-item--folder {
  cursor: pointer;
}

.file-item--folder:hover,
.file-item--selected {
  background: color-mix(in srgb, var(--n-border-color) 35%, transparent);
}

.file-item:not(.file-item--folder) {
  cursor: pointer;
}

.file-info {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.file-icon {
  flex-shrink: 0;
  margin-top: 2px;
  opacity: 0.7;
}

.file-name {
  font-size: 0.9rem;
  font-weight: 600;
  word-break: break-word;
}

.file-meta {
  margin-top: 2px;
  font-size: 0.75rem;
  color: var(--app-text-muted);
}

.file-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.receipts-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.receipts-nav-path {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--app-text-muted);
}

.receipts-toolbar {
  margin-top: 8px;
  padding: 4px 0;
}

.receipts-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--n-border-color);
  font-size: 0.9rem;
  font-weight: 600;
}

.receipts-footer-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
