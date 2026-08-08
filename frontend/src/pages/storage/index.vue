<script setup lang="ts">
import type { DataTableColumns, UploadFileInfo } from 'naive-ui'
import {
  NButton,
  NDataTable,
  NInput,
  NInputNumber,
  NModal,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NUpload,
  useMessage,
} from 'naive-ui'
import { ArrowLeft, Copy, Download, Eye, Folder, Link2, Pencil, Trash2, Upload } from 'lucide-vue-next'
import { computed, h, onMounted, ref, watch } from 'vue'

import {
  createVaultFolder,
  createVaultShareLink,
  deleteVaultFile,
  downloadGroupFile,
  downloadStorageReceipt,
  downloadStorageSalesBook,
  downloadVaultFile,
  getVaultFileContent,
  listGroupFileGroups,
  listGroupFiles,
  listVaultFiles,
  renameVaultFile,
  revokeShareLink,
  updateVaultFileContent,
  uploadVaultFile,
  type GroupChatFile,
  type StorageReceiptItem,
  type StorageReceiptPeriodGroup,
  type StorageSalesBookItem,
  type StorageSalesBookUnitGroup,
  type VaultFile,
} from '@/features/storage/api'
import { AppError } from '@/shared/api/http'
import { formatFileSize, maxUploadBytesFor, uploadLimitLabel } from '@/shared/config/uploads'
import { resolveAttachmentPreviewKind } from '@/shared/lib/attachment-preview-kind'
import AppCard from '@/shared/ui/AppCard.vue'
import {
  VIRTUAL_DATA_TABLE_MAX_HEIGHT,
  VIRTUAL_DATA_TABLE_MIN_ROW_HEIGHT,
} from '@/shared/ui/virtual-data-table'
import AttachmentPreviewModal from '@/widgets/chat/AttachmentPreviewModal.vue'
import { compareOptPeriodsDesc, formatOptPeriodLabel } from '@/features/leads/order-fields'
import { fetchReceiptsTree, peekReceiptsTree } from '@/features/storage/receipts-tree-cache'

type ReceiptFolderKind = 'main' | 'corrections' | 'sales_books'

interface ReceiptUnitFolder {
  inn: string
  name: string
  items: StorageReceiptItem[]
}

const message = useMessage()
const activeTab = ref('vault')
const vaultLoading = ref(false)
const receiptsLoading = ref(false)
const groupLoading = ref(false)
const vaultLoaded = ref(false)
const receiptsLoaded = ref(false)
const groupsLoaded = ref(false)

const vaultFiles = ref<VaultFile[]>([])
const vaultParentId = ref<number | null>(null)
const vaultPath = ref<{ id: number; name: string }[]>([])
const createFolderOpen = ref(false)
const createFolderName = ref('')
const createFolderLoading = ref(false)
const groupSummaries = ref<{ group_id: number; group_name: string; file_count: number }[]>([])
const groupFiles = ref<GroupChatFile[]>([])
const selectedGroupId = ref<number | null>(null)
const selectedChatId = ref<number | null>(null)

const vaultFolderItems = computed(() =>
  vaultFiles.value.filter((row) => row.is_folder),
)
const vaultFileItems = computed(() =>
  vaultFiles.value.filter((row) => !row.is_folder),
)
const receiptPeriods = ref<StorageReceiptPeriodGroup[]>([])
const selectedReceiptPeriod = ref<string | null>(null)
/** null = список типов папок внутри периода */
const receiptFolder = ref<ReceiptFolderKind | null>(null)
/** ООО внутри типа */
const storageUnitInn = ref<string | null>(null)
/** Buyer folder under sales-books lavka */
const storageBuyerInn = ref<string | null>(null)
const downloadingReceiptId = ref<number | null>(null)
const downloadingSalesBookId = ref<number | null>(null)

const shareModalOpen = ref(false)
const shareTarget = ref<VaultFile | null>(null)
const shareExpiresHours = ref<number | null>(168)
const shareMaxDownloads = ref<number | null>(null)
const sharePassword = ref('')
const shareLoading = ref(false)

const previewBlobUrl = ref<string | null>(null)
const previewBlob = ref<Blob | null>(null)
const previewName = ref('')
const previewOpen = ref(false)
const previewLoading = ref(false)

const previewMime = ref('')
const previewKind = computed(() =>
  previewName.value
    ? resolveAttachmentPreviewKind({ name: previewName.value, mime: previewMime.value })
    : 'unsupported',
)

const renameModalOpen = ref(false)
const renameTarget = ref<VaultFile | null>(null)
const renameValue = ref('')
const renameLoading = ref(false)

const editModalOpen = ref(false)
const editTarget = ref<VaultFile | null>(null)
const editContent = ref('')
const editLoading = ref(false)
const editSaving = ref(false)

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU')
}

async function loadVault(): Promise<void> {
  if (!vaultFiles.value.length) vaultLoading.value = true
  try {
    const data = await listVaultFiles({
      parent_id: vaultParentId.value,
      limit: 100,
    })
    vaultFiles.value = data.items
    vaultLoaded.value = true
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить файлы')
  } finally {
    vaultLoading.value = false
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

async function loadGroupSummaries(): Promise<void> {
  if (!groupSummaries.value.length) groupLoading.value = true
  try {
    const data = await listGroupFileGroups()
    groupSummaries.value = data.items
    groupsLoaded.value = true
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить группы')
  } finally {
    groupLoading.value = false
  }
}

async function loadReceipts(opts?: { force?: boolean }): Promise<void> {
  const cached = peekReceiptsTree()
  if (cached?.length) {
    receiptPeriods.value = [...cached].sort((a, b) =>
      compareOptPeriodsDesc(a.period_code, b.period_code),
    )
    if (!selectedReceiptPeriod.value && receiptPeriods.value.length > 0) {
      selectedReceiptPeriod.value = receiptPeriods.value[0].period_code
    }
    receiptsLoaded.value = true
  }
  if (!receiptPeriods.value.length) receiptsLoading.value = true
  try {
    const data = await fetchReceiptsTree(opts)
    receiptPeriods.value = [...data.periods].sort((a, b) =>
      compareOptPeriodsDesc(a.period_code, b.period_code),
    )
    if (!selectedReceiptPeriod.value && receiptPeriods.value.length > 0) {
      selectedReceiptPeriod.value = receiptPeriods.value[0].period_code
    }
    receiptsLoaded.value = true
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить квитанции')
  } finally {
    receiptsLoading.value = false
  }
}

const selectedPeriodGroup = computed(() => {
  const period = selectedReceiptPeriod.value
  if (!period) return null
  return receiptPeriods.value.find((row) => row.period_code === period) ?? null
})

const selectedPeriodAllItems = computed(() => selectedPeriodGroup.value?.items ?? [])

const selectedReceiptMainItems = computed(() =>
  selectedPeriodAllItems.value.filter((row) => !row.is_correction),
)

const selectedReceiptCorrectionItems = computed(() =>
  selectedPeriodAllItems.value.filter((row) => !!row.is_correction),
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

const selectedSalesBookUnits = computed((): StorageSalesBookUnitGroup[] => {
  const nested = selectedPeriodGroup.value?.sales_book_units ?? []
  if (nested.length) return nested
  // fallback: сгруппировать плоский список по продавцу
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
  return [...byInn.values()].sort((a, b) =>
    a.seller_name.localeCompare(b.seller_name, 'ru'),
  )
})

const receiptUnitFolders = computed((): ReceiptUnitFolder[] => {
  const items =
    receiptFolder.value === 'corrections'
      ? selectedReceiptCorrectionItems.value
      : selectedReceiptMainItems.value
  const byInn = new Map<string, ReceiptUnitFolder>()
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

interface SalesBuyerFolder {
  inn: string
  name: string
  items: StorageSalesBookItem[]
}

const selectedSalesBuyerFolders = computed((): SalesBuyerFolder[] => {
  if (!storageUnitInn.value || receiptFolder.value !== 'sales_books') return []
  const unit = selectedSalesBookUnits.value.find((u) => u.seller_inn === storageUnitInn.value)
  if (!unit) return []
  const byBuyer = new Map<string, SalesBuyerFolder>()
  for (const item of unit.orders.flatMap((o) => o.items)) {
    const inn = item.buyer_inn
    if (!inn) continue
    let folder = byBuyer.get(inn)
    if (!folder) {
      folder = {
        inn,
        name: shortLavkaName(item.buyer_name) || item.buyer_name || inn,
        items: [],
      }
      byBuyer.set(inn, folder)
    } else if (item.buyer_name && folder.name === inn) {
      folder.name = shortLavkaName(item.buyer_name) || item.buyer_name
    }
    folder.items.push(item)
  }
  return [...byBuyer.values()].sort((a, b) => a.name.localeCompare(b.name, 'ru'))
})

const selectedSalesBookItems = computed((): StorageSalesBookItem[] => {
  if (!storageUnitInn.value || !storageBuyerInn.value) return []
  return (
    selectedSalesBuyerFolders.value.find((f) => f.inn === storageBuyerInn.value)?.items ?? []
  )
})

const selectedReceiptUnitItems = computed((): StorageReceiptItem[] => {
  if (!storageUnitInn.value) return []
  return receiptUnitFolders.value.find((u) => u.inn === storageUnitInn.value)?.items ?? []
})

const receiptFolderLabel = computed(() => {
  if (receiptFolder.value === 'main') return 'Основные'
  if (receiptFolder.value === 'corrections') return 'Корректировки'
  if (receiptFolder.value === 'sales_books') return 'Книги продаж'
  return ''
})

const selectedUnitLabel = computed(() => {
  if (!storageUnitInn.value) return ''
  if (receiptFolder.value === 'sales_books') {
    const unit = selectedSalesBookUnits.value.find((u) => u.seller_inn === storageUnitInn.value)
    return shortLavkaName(unit?.seller_name) || unit?.seller_name || storageUnitInn.value
  }
  const unit = receiptUnitFolders.value.find((u) => u.inn === storageUnitInn.value)
  return unit?.name || storageUnitInn.value
})

const selectedBuyerLabel = computed(() => {
  if (!storageBuyerInn.value) return ''
  const folder = selectedSalesBuyerFolders.value.find((f) => f.inn === storageBuyerInn.value)
  return folder?.name || storageBuyerInn.value
})

function openReceiptPeriod(periodCode: string): void {
  selectedReceiptPeriod.value = periodCode
  receiptFolder.value = null
  storageUnitInn.value = null
  storageBuyerInn.value = null
}

function openReceiptFolder(kind: ReceiptFolderKind): void {
  receiptFolder.value = kind
  storageUnitInn.value = null
  storageBuyerInn.value = null
}

function openReceiptUnit(inn: string): void {
  storageUnitInn.value = inn
  storageBuyerInn.value = null
}

function openSalesBuyer(inn: string): void {
  storageBuyerInn.value = inn
}

function receiptsBack(): void {
  if (storageBuyerInn.value) {
    storageBuyerInn.value = null
    return
  }
  if (storageUnitInn.value) {
    storageUnitInn.value = null
    return
  }
  if (receiptFolder.value) {
    receiptFolder.value = null
    return
  }
  selectedReceiptPeriod.value = null
}

function receiptKindLabel(kind: string, isCorrection = false): string {
  const base = kind === 'notice' ? 'Извещение о вводе' : 'Квитанция о приеме'
  return isCorrection ? `${base} · корректировка` : base
}

async function onDownloadSalesBook(row: StorageSalesBookItem): Promise<void> {
  downloadingSalesBookId.value = row.id
  try {
    const blob = await downloadStorageSalesBook(row.id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = row.source_filename || `sales-book-${row.id}.pdf`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать книгу продаж')
  } finally {
    downloadingSalesBookId.value = null
  }
}

async function onDownloadReceipt(row: StorageReceiptItem): Promise<void> {
  downloadingReceiptId.value = row.id
  try {
    const blob = await downloadStorageReceipt(row.id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = row.source_filename || `receipt-${row.id}.pdf`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать квитанцию')
  } finally {
    downloadingReceiptId.value = null
  }
}

async function loadGroupFiles(): Promise<void> {
  if (selectedGroupId.value == null) {
    groupFiles.value = []
    return
  }
  if (!groupFiles.value.length) groupLoading.value = true
  try {
    const data = await listGroupFiles({ group_id: selectedGroupId.value, limit: 200 })
    groupFiles.value = data.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить файлы чатов')
  } finally {
    groupLoading.value = false
  }
}

async function openGroupFolder(groupId: number): Promise<void> {
  selectedGroupId.value = groupId
  selectedChatId.value = null
  groupFiles.value = []
  await loadGroupFiles()
}

function openChatFolder(chatId: number): void {
  selectedChatId.value = chatId
}

function groupFilesBack(): void {
  if (selectedChatId.value != null) {
    selectedChatId.value = null
    return
  }
  selectedGroupId.value = null
  groupFiles.value = []
}

async function ensureActiveTabLoaded(): Promise<void> {
  if (activeTab.value === 'vault' && !vaultLoaded.value) await loadVault()
  else if (activeTab.value === 'receipts' && !receiptsLoaded.value) await loadReceipts()
  else if (activeTab.value === 'group' && !groupsLoaded.value) await loadGroupSummaries()
}

async function onVaultUpload(data: { file: UploadFileInfo }): Promise<boolean> {
  const file = data.file.file
  if (!file) return false
  if (file.size > maxUploadBytesFor(file)) {
    message.error(`Файл слишком большой (макс. ${uploadLimitLabel(file)})`)
    return false
  }
  try {
    await uploadVaultFile(file, { parent_id: vaultParentId.value })
    message.success('Файл добавлен в хранилище')
    await loadVault()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка загрузки')
  }
  return false
}

async function onDeleteVault(row: VaultFile): Promise<void> {
  try {
    await deleteVaultFile(row.id)
    message.success(row.is_folder ? 'Папка удалена' : 'Файл удалён')
    await loadVault()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось удалить')
  }
}

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}

async function onDownloadVault(row: VaultFile): Promise<void> {
  try {
    const blob = await downloadVaultFile(row.id)
    triggerBlobDownload(blob, row.original_name)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать файл')
  }
}

function openRenameModal(row: VaultFile): void {
  renameTarget.value = row
  renameValue.value = row.original_name
  renameModalOpen.value = true
}

async function submitRename(): Promise<void> {
  if (!renameTarget.value) return
  const name = renameValue.value.trim()
  if (!name) {
    message.error('Имя файла не может быть пустым')
    return
  }
  renameLoading.value = true
  try {
    await renameVaultFile(renameTarget.value.id, name)
    message.success('Файл переименован')
    renameModalOpen.value = false
    await loadVault()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось переименовать')
  } finally {
    renameLoading.value = false
  }
}

async function openEditModal(row: VaultFile): Promise<void> {
  editTarget.value = row
  editContent.value = ''
  editModalOpen.value = true
  editLoading.value = true
  try {
    const data = await getVaultFileContent(row.id)
    if (!data.editable) {
      message.warning('Этот файл нельзя редактировать как текст')
      editModalOpen.value = false
      return
    }
    editContent.value = data.content
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось открыть файл')
    editModalOpen.value = false
  } finally {
    editLoading.value = false
  }
}

async function submitEdit(): Promise<void> {
  if (!editTarget.value) return
  editSaving.value = true
  try {
    await updateVaultFileContent(editTarget.value.id, editContent.value)
    message.success('Файл сохранён')
    editModalOpen.value = false
    await loadVault()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить')
  } finally {
    editSaving.value = false
  }
}

const EDITABLE_EXTENSIONS = new Set([
  'txt', 'md', 'markdown', 'csv', 'tsv', 'log', 'json', 'xml', 'yaml', 'yml',
  'html', 'htm', 'css', 'scss', 'js', 'ts', 'jsx', 'tsx', 'vue', 'py', 'java',
  'c', 'cpp', 'h', 'hpp', 'go', 'rs', 'rb', 'php', 'sh', 'bat', 'ps1', 'sql',
  'ini', 'conf', 'cfg', 'toml', 'env', 'rst',
])

function isEditable(row: VaultFile): boolean {
  if (row.is_folder || row.file_id == null) return false
  if (row.size_bytes > 1_000_000) return false
  const mime = (row.mime_type || '').toLowerCase()
  if (mime.startsWith('text/')) return true
  if (
    ['application/json', 'application/xml', 'application/x-yaml', 'application/javascript'].includes(
      mime,
    )
  ) {
    return true
  }
  const ext = row.original_name.includes('.')
    ? row.original_name.split('.').pop()!.toLowerCase()
    : ''
  return EDITABLE_EXTENSIONS.has(ext)
}

function openShareModal(row: VaultFile): void {
  if (row.is_folder || row.file_id == null) {
    message.warning('Ссылку можно создать только для файла')
    return
  }
  shareTarget.value = row
  shareExpiresHours.value = 168
  shareMaxDownloads.value = null
  sharePassword.value = ''
  shareModalOpen.value = true
}

async function submitShare(): Promise<void> {
  if (!shareTarget.value?.file_id) return
  shareLoading.value = true
  try {
    const link = await createVaultShareLink(shareTarget.value.file_id, {
      expires_in_hours: shareExpiresHours.value,
      max_downloads: shareMaxDownloads.value,
      password: sharePassword.value.trim() || null,
    })
    await navigator.clipboard.writeText(link.url)
    message.success('Ссылка создана и скопирована')
    shareModalOpen.value = false
    await loadVault()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось создать ссылку')
  } finally {
    shareLoading.value = false
  }
}

async function onRevokeShare(shareId: number): Promise<void> {
  try {
    await revokeShareLink(shareId)
    message.success('Ссылка отозвана')
    await loadVault()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка')
  }
}

function copyText(text: string): void {
  void navigator.clipboard.writeText(text)
  message.success('Скопировано')
}

function resetPreviewBlob(): void {
  if (previewBlobUrl.value) URL.revokeObjectURL(previewBlobUrl.value)
  previewBlobUrl.value = null
  previewBlob.value = null
}

async function openPreview(
  name: string,
  mime: string,
  load: () => Promise<Blob>,
): Promise<void> {
  resetPreviewBlob()
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
  resetPreviewBlob()
}

async function previewGroupFile(row: GroupChatFile): Promise<void> {
  await openPreview(row.original_name, row.mime_type || '', () => downloadGroupFile(row.id))
}

async function previewVaultFile(row: VaultFile): Promise<void> {
  await openPreview(row.original_name, row.mime_type || '', () => downloadVaultFile(row.id))
}

const vaultColumns = computed<DataTableColumns<VaultFile>>(() => [
  { title: 'Имя', key: 'original_name', ellipsis: { tooltip: true } },
  {
    title: 'Размер',
    key: 'size_bytes',
    width: 100,
    render: (row) => formatFileSize(row.size_bytes),
  },
  {
    title: 'Загружен',
    key: 'created_at',
    width: 160,
    render: (row) => formatDate(row.created_at),
  },
  {
    title: 'Ссылки',
    key: 'share_links',
    width: 200,
    render: (row) =>
      row.share_links.length
        ? row.share_links
            .map((s) => `${s.download_count}/${s.max_downloads ?? '∞'}`)
            .join(', ')
        : '—',
  },
  {
    title: '',
    key: 'actions',
    width: 300,
    render: (row) =>
      h(NSpace, { size: 4, wrap: false }, () => [
        h(
          NButton,
          {
            size: 'small',
            quaternary: true,
            title: 'Предпросмотр',
            onClick: () => previewVaultFile(row),
          },
          { icon: () => h(Eye, { size: 14 }) },
        ),
        h(
          NButton,
          {
            size: 'small',
            quaternary: true,
            title: 'Скачать',
            onClick: () => onDownloadVault(row),
          },
          { icon: () => h(Download, { size: 14 }) },
        ),
        ...(isEditable(row)
          ? [
              h(
                NButton,
                {
                  size: 'small',
                  quaternary: true,
                  title: 'Редактировать',
                  onClick: () => openEditModal(row),
                },
                { icon: () => h(Pencil, { size: 14 }) },
              ),
            ]
          : []),
        h(
          NButton,
          { size: 'small', quaternary: true, title: 'Переименовать', onClick: () => openRenameModal(row) },
          { default: () => 'Имя' },
        ),
        h(
          NButton,
          { size: 'small', quaternary: true, onClick: () => openShareModal(row) },
          { icon: () => h(Link2, { size: 14 }), default: () => 'Ссылка' },
        ),
        h(
          NButton,
          { size: 'small', quaternary: true, type: 'error', title: 'Удалить', onClick: () => onDeleteVault(row) },
          { icon: () => h(Trash2, { size: 14 }) },
        ),
      ]),
  },
])

const groupChatFolders = computed(() => {
  const map = new Map<number, { chatId: number; chatLabel: string; files: GroupChatFile[] }>()
  for (const file of groupFiles.value) {
    const label = file.contact_name
      ? `${file.contact_name} (чат #${file.chat_id})`
      : `Чат #${file.chat_id}`
    const bucket = map.get(file.chat_id)
    if (bucket) {
      bucket.files.push(file)
    } else {
      map.set(file.chat_id, { chatId: file.chat_id, chatLabel: label, files: [file] })
    }
  }
  return [...map.values()].sort((a, b) => a.chatLabel.localeCompare(b.chatLabel, 'ru'))
})

const selectedGroupLabel = computed(() => {
  if (selectedGroupId.value == null) return ''
  return (
    groupSummaries.value.find((g) => g.group_id === selectedGroupId.value)?.group_name ||
    `Группа #${selectedGroupId.value}`
  )
})

const selectedChatLabel = computed(() => {
  if (selectedChatId.value == null) return ''
  return (
    groupChatFolders.value.find((c) => c.chatId === selectedChatId.value)?.chatLabel ||
    `Чат #${selectedChatId.value}`
  )
})

const selectedChatFiles = computed(() => {
  if (selectedChatId.value == null) return [] as GroupChatFile[]
  return (
    groupChatFolders.value.find((c) => c.chatId === selectedChatId.value)?.files ?? []
  )
})

const groupColumns = computed<DataTableColumns<GroupChatFile>>(() => [
  { title: 'Файл', key: 'original_name', ellipsis: { tooltip: true } },
  {
    title: 'От кого',
    key: 'sender_display_name',
    width: 180,
    render: (row) => {
      const name = (row.sender_display_name || row.contact_name || '').trim()
      if (row.direction === 'inbound') {
        const client = name && name !== 'Оператор' ? name : row.contact_name || 'Клиент'
        return `Клиент: ${client}`
      }
      const operator = name && name !== 'Оператор' ? name : 'Оператор'
      return `Оператор: ${operator}`
    },
  },
  {
    title: 'Когда',
    key: 'created_at',
    width: 160,
    render: (row) => formatDate(row.created_at),
  },
  {
    title: 'Размер',
    key: 'size_bytes',
    width: 90,
    render: (row) => formatFileSize(row.size_bytes),
  },
  {
    title: '',
    key: 'actions',
    width: 100,
    render: (row) =>
      h(
        NButton,
        { size: 'small', onClick: () => previewGroupFile(row) },
        { default: () => 'Открыть' },
      ),
  },
])

watch(activeTab, () => {
  void ensureActiveTabLoaded()
})

onMounted(() => {
  void ensureActiveTabLoaded()
})
</script>

<template>
  <div class="storage-page">
    <AppCard title="Хранилище файлов">
      <NTabs v-model:value="activeTab" type="line" animated>
        <NTabPane name="vault" tab="Мои файлы">
          <NSpace vertical :size="16">
            <p class="hint">
              Личные файлы для отправки в чаты. Чтобы передать файл по ссылке без входа — откройте
              <a href="/share" target="_blank" rel="noopener">/share</a>.
            </p>
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
            <NSpace>
              <NButton secondary @click="openCreateFolder">
                <template #icon><Folder :size="16" /></template>
                Создать папку
              </NButton>
              <NUpload :show-file-list="false" @before-upload="onVaultUpload">
                <NButton type="primary">
                  <template #icon><Upload :size="16" /></template>
                  Загрузить файл
                </NButton>
              </NUpload>
            </NSpace>
            <NSpin :show="vaultLoading && vaultFiles.length === 0">
              <ul v-if="vaultFolderItems.length" class="explorer-list">
                <li
                  v-for="folder in vaultFolderItems"
                  :key="folder.id"
                  class="explorer-item"
                  @click="openVaultFolder(folder)"
                >
                  <Folder :size="18" class="explorer-icon" />
                  <span class="explorer-name">{{ folder.original_name }}</span>
                  <NButton
                    size="tiny"
                    quaternary
                    type="error"
                    @click.stop="onDeleteVault(folder)"
                  >
                    <Trash2 :size="14" />
                  </NButton>
                </li>
              </ul>
              <NDataTable
                v-if="vaultFileItems.length || !vaultFolderItems.length"
                :columns="vaultColumns"
                :data="vaultFileItems"
                :bordered="false"
                virtual-scroll
                :max-height="VIRTUAL_DATA_TABLE_MAX_HEIGHT"
                :min-row-height="VIRTUAL_DATA_TABLE_MIN_ROW_HEIGHT"
              />
              <p
                v-if="!vaultLoading && !vaultFolderItems.length && !vaultFileItems.length"
                class="empty-hint"
              >
                В этой папке пусто
              </p>
            </NSpin>
            <div v-for="file in vaultFileItems" :key="file.id" class="share-list">
              <template v-for="link in file.share_links" :key="link.id">
                <div class="share-row">
                  <span class="share-url">{{ link.url }}</span>
                  <NButton size="tiny" quaternary @click="copyText(link.url)">
                    <Copy :size="12" />
                  </NButton>
                  <NButton size="tiny" quaternary type="error" @click="onRevokeShare(link.id)">
                    Отозвать
                  </NButton>
                </div>
              </template>
            </div>
          </NSpace>
        </NTabPane>

        <NTabPane name="receipts" tab="Квитанции">
          <NSpin :show="receiptsLoading && receiptPeriods.length === 0">
            <div v-if="selectedReceiptPeriod" class="explorer-nav">
              <NButton size="tiny" quaternary @click="receiptsBack">
                <template #icon><ArrowLeft :size="14" /></template>
                Назад
              </NButton>
              <div class="explorer-path">
                <button
                  type="button"
                  class="explorer-crumb"
                  @click="
                    selectedReceiptPeriod = null
                    receiptFolder = null
                    storageUnitInn = null
                    storageBuyerInn = null
                  "
                >
                  Квитанции
                </button>
                <span class="explorer-sep">/</span>
                <button
                  type="button"
                  class="explorer-crumb"
                  @click="receiptFolder = null; storageUnitInn = null; storageBuyerInn = null"
                >
                  {{ formatOptPeriodLabel(selectedReceiptPeriod) || selectedReceiptPeriod }}
                </button>
                <template v-if="receiptFolder">
                  <span class="explorer-sep">/</span>
                  <button
                    type="button"
                    class="explorer-crumb"
                    @click="storageUnitInn = null; storageBuyerInn = null"
                  >
                    {{ receiptFolderLabel }}
                  </button>
                </template>
                <template v-if="storageUnitInn">
                  <span class="explorer-sep">/</span>
                  <button
                    type="button"
                    class="explorer-crumb"
                    :class="{ 'explorer-crumb--current': !storageBuyerInn }"
                    @click="storageBuyerInn = null"
                  >
                    {{ selectedUnitLabel }}
                  </button>
                </template>
                <template v-if="storageBuyerInn">
                  <span class="explorer-sep">/</span>
                  <span class="explorer-crumb explorer-crumb--current">{{ selectedBuyerLabel }}</span>
                </template>
              </div>
            </div>

            <!-- periods -->
            <ul v-if="!selectedReceiptPeriod" class="explorer-list">
              <li
                v-for="period in receiptPeriods"
                :key="period.period_code"
                class="explorer-item"
                @click="openReceiptPeriod(period.period_code)"
              >
                <Folder :size="18" class="explorer-icon" />
                <span class="explorer-name">
                  {{ formatOptPeriodLabel(period.period_code) || period.period_code }}
                </span>
              </li>
              <li v-if="!receiptPeriods.length && !receiptsLoading" class="empty-hint">Квитанций пока нет</li>
            </ul>

            <!-- type folders -->
            <ul v-else-if="!receiptFolder" class="explorer-list">
              <li
                v-if="selectedReceiptMainItems.length"
                class="explorer-item"
                @click="openReceiptFolder('main')"
              >
                <Folder :size="18" class="explorer-icon" />
                <span class="explorer-name">Основные</span>
              </li>
              <li
                v-if="selectedReceiptCorrectionItems.length"
                class="explorer-item"
                @click="openReceiptFolder('corrections')"
              >
                <Folder :size="18" class="explorer-icon" />
                <span class="explorer-name">Корректировки</span>
              </li>
              <li
                v-if="selectedSalesBookUnits.length"
                class="explorer-item"
                @click="openReceiptFolder('sales_books')"
              >
                <Folder :size="18" class="explorer-icon" />
                <span class="explorer-name">Книги продаж</span>
              </li>
              <li
                v-if="
                  !selectedReceiptMainItems.length &&
                  !selectedReceiptCorrectionItems.length &&
                  !selectedSalesBookUnits.length
                "
                class="empty-hint"
              >
                В этом периоде пусто
              </li>
            </ul>

            <!-- ООО folders -->
            <ul
              v-else-if="!storageUnitInn && receiptFolder === 'sales_books'"
              class="explorer-list"
            >
              <li
                v-for="unit in selectedSalesBookUnits"
                :key="unit.seller_inn"
                class="explorer-item"
                @click="openReceiptUnit(unit.seller_inn)"
              >
                <Folder :size="18" class="explorer-icon" />
                <span class="explorer-name">
                  {{ shortLavkaName(unit.seller_name) || unit.seller_name }}
                </span>
              </li>
            </ul>
            <ul
              v-else-if="!storageUnitInn && (receiptFolder === 'main' || receiptFolder === 'corrections')"
              class="explorer-list"
            >
              <li
                v-for="unit in receiptUnitFolders"
                :key="unit.inn"
                class="explorer-item"
                @click="openReceiptUnit(unit.inn)"
              >
                <Folder :size="18" class="explorer-icon" />
                <span class="explorer-name">{{ unit.name }}</span>
              </li>
              <li v-if="!receiptUnitFolders.length" class="empty-hint">Папок нет</li>
            </ul>

            <!-- buyer folders under lavka (sales books) -->
            <ul
              v-else-if="
                receiptFolder === 'sales_books' && storageUnitInn && !storageBuyerInn
              "
              class="explorer-list"
            >
              <li
                v-for="buyer in selectedSalesBuyerFolders"
                :key="buyer.inn"
                class="explorer-item"
                @click="openSalesBuyer(buyer.inn)"
              >
                <Folder :size="18" class="explorer-icon" />
                <span class="explorer-name">{{ buyer.name }}</span>
              </li>
              <li v-if="!selectedSalesBuyerFolders.length" class="empty-hint">
                Покупателей нет
              </li>
            </ul>

            <!-- files: sales books -->
            <div
              v-else-if="
                receiptFolder === 'sales_books' && storageBuyerInn && selectedSalesBookItems.length
              "
              class="receipts-list"
            >
              <div
                v-for="row in selectedSalesBookItems"
                :key="`sb-${row.id}`"
                class="receipts-row"
              >
                <div
                  class="receipts-main receipts-main--clickable"
                  @click="
                    row.has_pdf &&
                      openPreview(
                        row.source_filename || `sales-book-${row.id}.pdf`,
                        'application/pdf',
                        () => downloadStorageSalesBook(row.id),
                      )
                  "
                >
                  <div class="receipts-title">{{ row.source_filename }}</div>
                  <div class="receipts-meta">ИНН {{ row.buyer_inn }}</div>
                </div>
                <NSpace :size="8">
                  <NButton
                    size="small"
                    type="primary"
                    secondary
                    :loading="downloadingSalesBookId === row.id"
                    :disabled="!row.has_pdf"
                    @click="
                      openPreview(
                        row.source_filename || `sales-book-${row.id}.pdf`,
                        'application/pdf',
                        () => downloadStorageSalesBook(row.id),
                      )
                    "
                  >
                    Открыть
                  </NButton>
                  <NButton
                    size="small"
                    secondary
                    :loading="downloadingSalesBookId === row.id"
                    :disabled="!row.has_pdf"
                    @click="onDownloadSalesBook(row)"
                  >
                    Скачать
                  </NButton>
                </NSpace>
              </div>
            </div>

            <!-- files: receipts -->
            <div
              v-else-if="receiptFolder !== 'sales_books' && selectedReceiptUnitItems.length"
              class="receipts-list"
            >
              <div
                v-for="row in selectedReceiptUnitItems"
                :key="row.id"
                class="receipts-row"
              >
                <div
                  class="receipts-main receipts-main--clickable"
                  @click="
                    row.has_pdf &&
                      openPreview(
                        row.source_filename || `receipt-${row.id}.pdf`,
                        'application/pdf',
                        () => downloadStorageReceipt(row.id),
                      )
                  "
                >
                  <div class="receipts-title">{{ row.source_filename }}</div>
                  <div class="receipts-meta">
                    {{ receiptKindLabel(row.doc_kind, !!row.is_correction) }}
                  </div>
                </div>
                <NSpace :size="8">
                  <NButton
                    size="small"
                    type="primary"
                    secondary
                    :loading="downloadingReceiptId === row.id"
                    :disabled="!row.has_pdf"
                    @click="
                      openPreview(
                        row.source_filename || `receipt-${row.id}.pdf`,
                        'application/pdf',
                        () => downloadStorageReceipt(row.id),
                      )
                    "
                  >
                    Открыть
                  </NButton>
                  <NButton
                    size="small"
                    secondary
                    :loading="downloadingReceiptId === row.id"
                    :disabled="!row.has_pdf"
                    @click="onDownloadReceipt(row)"
                  >
                    Скачать
                  </NButton>
                </NSpace>
              </div>
            </div>
            <p v-else-if="storageBuyerInn || storageUnitInn" class="empty-hint">
              В этой папке пусто
            </p>
          </NSpin>
        </NTabPane>

        <NTabPane name="group" tab="Файлы из чатов">
          <NSpin :show="groupLoading && !groupSummaries.length && selectedGroupId == null">
            <div v-if="selectedGroupId != null" class="explorer-nav">
              <NButton size="tiny" quaternary @click="groupFilesBack">
                <template #icon><ArrowLeft :size="14" /></template>
                Назад
              </NButton>
              <div class="explorer-path">
                <button
                  type="button"
                  class="explorer-crumb"
                  @click="selectedGroupId = null; selectedChatId = null; groupFiles = []"
                >
                  Группы
                </button>
                <span class="explorer-sep">/</span>
                <button
                  type="button"
                  class="explorer-crumb"
                  :class="{ 'explorer-crumb--current': selectedChatId == null }"
                  @click="selectedChatId = null"
                >
                  {{ selectedGroupLabel }}
                </button>
                <template v-if="selectedChatId != null">
                  <span class="explorer-sep">/</span>
                  <span class="explorer-crumb explorer-crumb--current">{{ selectedChatLabel }}</span>
                </template>
              </div>
            </div>

            <ul v-if="selectedGroupId == null" class="explorer-list">
              <li
                v-for="g in groupSummaries"
                :key="g.group_id"
                class="explorer-item"
                @click="openGroupFolder(g.group_id)"
              >
                <Folder :size="18" class="explorer-icon" />
                <span class="explorer-name">{{ g.group_name }}</span>
                <span class="explorer-meta">{{ g.file_count }}</span>
              </li>
              <li v-if="!groupSummaries.length && !groupLoading" class="empty-hint">
                Групп с файлами пока нет
              </li>
            </ul>

            <ul
              v-else-if="selectedChatId == null"
              class="explorer-list"
            >
              <li
                v-for="chat in groupChatFolders"
                :key="chat.chatId"
                class="explorer-item"
                @click="openChatFolder(chat.chatId)"
              >
                <Folder :size="18" class="explorer-icon" />
                <span class="explorer-name">{{ chat.chatLabel }}</span>
                <span class="explorer-meta">{{ chat.files.length }}</span>
              </li>
              <li v-if="!groupChatFolders.length && !groupLoading" class="empty-hint">
                В этой группе пока нет файлов из чатов
              </li>
            </ul>

            <div v-else>
              <NDataTable
                :columns="groupColumns"
                :data="selectedChatFiles"
                :bordered="false"
                size="small"
                virtual-scroll
                :max-height="480"
                :min-row-height="VIRTUAL_DATA_TABLE_MIN_ROW_HEIGHT"
              />
              <p v-if="!selectedChatFiles.length && !groupLoading" class="empty-hint">
                В этом чате пока нет файлов
              </p>
            </div>
          </NSpin>
        </NTabPane>
      </NTabs>
    </AppCard>

    <NModal
      v-model:show="createFolderOpen"
      preset="card"
      title="Новая папка"
      style="width: 400px; max-width: 94vw"
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

    <NModal v-model:show="shareModalOpen" preset="card" title="Ссылка на файл" style="width: 420px">
      <NSpace vertical>
        <p>{{ shareTarget?.original_name }}</p>
        <p class="hint">Получатель увидит только файл — без вашего имени и аккаунта.</p>
        <NInputNumber
          v-model:value="shareExpiresHours"
          :min="1"
          :max="8760"
          placeholder="Срок действия (часы)"
          style="width: 100%"
        />
        <NInputNumber
          v-model:value="shareMaxDownloads"
          :min="1"
          placeholder="Лимит скачиваний"
          style="width: 100%"
          clearable
        />
        <NInput
          v-model:value="sharePassword"
          type="password"
          placeholder="Пароль"
          show-password-on="click"
        />
        <NButton type="primary" :loading="shareLoading" block @click="submitShare">
          Создать и скопировать
        </NButton>
      </NSpace>
    </NModal>

    <NModal
      v-model:show="renameModalOpen"
      preset="card"
      title="Переименовать файл"
      style="width: 420px"
    >
      <NSpace vertical>
        <NInput
          v-model:value="renameValue"
          placeholder="Новое имя файла"
          @keyup.enter="submitRename"
        />
        <NButton type="primary" :loading="renameLoading" block @click="submitRename">
          Сохранить
        </NButton>
      </NSpace>
    </NModal>

    <NModal
      v-model:show="editModalOpen"
      preset="card"
      :title="`Редактирование: ${editTarget?.original_name ?? ''}`"
      style="width: 80vw; max-width: 900px"
    >
      <NSpin :show="editLoading">
        <NInput
          v-model:value="editContent"
          type="textarea"
          :autosize="{ minRows: 16, maxRows: 28 }"
          placeholder="Содержимое файла"
          class="editor-textarea"
        />
      </NSpin>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="editModalOpen = false">Отмена</NButton>
          <NButton
            type="primary"
            :loading="editSaving"
            :disabled="editLoading"
            @click="submitEdit"
          >
            Сохранить
          </NButton>
        </NSpace>
      </template>
    </NModal>

    <AttachmentPreviewModal
      :open="previewOpen"
      :loading="previewLoading"
      :label="previewName"
      :blob-url="previewBlobUrl"
      :blob="previewBlob"
      :preview-kind="previewKind"
      @close="closePreview"
    />
  </div>
</template>

<style scoped>
.storage-page {
  width: 100%;
  padding-bottom: 16px;
}

.chat-block {
  margin-bottom: 24px;
}

.chat-block-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}

.share-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-top: 4px;
}

.share-url {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-text-muted);
}

.hint,
.empty-hint {
  color: var(--app-text-muted);
  font-size: 0.8125rem;
}

.editor-textarea :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
}

.explorer-nav {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.explorer-path {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  font-size: 0.88rem;
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

.explorer-meta {
  margin-left: auto;
  font-size: 0.8rem;
  color: var(--app-text-muted);
}

.explorer-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--app-surface, #fff);
}

.explorer-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid color-mix(in srgb, var(--app-border) 70%, transparent);
}

.explorer-item:last-child {
  border-bottom: 0;
}

.explorer-item:hover {
  background: color-mix(in srgb, var(--app-accent) 8%, transparent);
}

.explorer-icon {
  flex-shrink: 0;
  color: #ca8a04;
}

.explorer-name {
  font-weight: 560;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.receipts-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.receipts-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
}
.receipts-main {
  min-width: 0;
  flex: 1;
}
.receipts-main--clickable {
  cursor: pointer;
}
.receipts-main--clickable:hover .receipts-title {
  text-decoration: underline;
}
.receipts-title {
  font-weight: 600;
}
.receipts-meta {
  margin-top: 2px;
  font-size: 0.85rem;
  opacity: 0.75;
}
</style>
