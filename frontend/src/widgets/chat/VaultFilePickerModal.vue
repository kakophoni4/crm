<script setup lang="ts">
import {
  NButton,
  NCheckbox,
  NEmpty,
  NModal,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  NTooltip,
  useMessage,
} from 'naive-ui'
import { ArrowLeft, Download, Eye, FileText, FolderOpen, FolderPlus, Send } from 'lucide-vue-next'
import { computed, onUnmounted, ref, watch } from 'vue'

import { uploadFile } from '@/features/chats/api'
import {
  downloadGroupFile,
  downloadStorageReceipt,
  downloadStorageSalesBook,
  listGroupFiles,
  listStorageReceiptsTree,
  listVaultFiles,
  uploadVaultFile,
  type GroupChatFile,
  type StorageReceiptItem,
  type StorageReceiptPeriodGroup,
  type StorageSalesBookItem,
  type VaultFile,
} from '@/features/storage/api'
import { AppError } from '@/shared/api/http'
import {
  attachmentPreviewSupported,
  resolveAttachmentPreviewKind,
} from '@/shared/lib/attachment-preview-kind'
import { formatFileSize } from '@/shared/config/uploads'
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
const dialogFiles = ref<GroupChatFile[]>([])
const receiptPeriods = ref<StorageReceiptPeriodGroup[]>([])
const receiptPeriod = ref<string | null>(null)
/** null = period root; folder inside period */
const receiptFolder = ref<'main' | 'corrections' | 'sales_books' | null>(null)
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

const periodSalesBookItems = computed((): StorageSalesBookItem[] => {
  const items = selectedPeriodGroup.value?.sales_books ?? []
  return [...items].sort((a, b) => {
    const sa = (a.seller_name || a.seller_inn || '').localeCompare(
      b.seller_name || b.seller_inn || '',
      'ru',
    )
    if (sa !== 0) return sa
    return a.buyer_inn.localeCompare(b.buyer_inn)
  })
})

const visibleReceiptItems = computed(() => {
  if (receiptFolder.value === 'corrections') return periodCorrectionItems.value
  if (receiptFolder.value === 'main') return periodMainItems.value
  return []
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
    const hit = (period.sales_books ?? []).find((row) => row.id === id)
    if (hit) return hit
  }
  return null
}

function periodSalesBooksCount(period: StorageReceiptPeriodGroup): number {
  return period.sales_books?.length ?? 0
}

async function loadVault(): Promise<void> {
  loading.value = true
  try {
    const data = await listVaultFiles({ limit: 100 })
    vaultFiles.value = data.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить хранилище')
  } finally {
    loading.value = false
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
  loading.value = true
  try {
    const data = await listStorageReceiptsTree()
    receiptPeriods.value = [...data.periods].sort((a, b) =>
      compareOptPeriodsDesc(a.period_code, b.period_code),
    )
    if (
      receiptPeriod.value &&
      !data.periods.some((row) => row.period_code === receiptPeriod.value)
    ) {
      receiptPeriod.value = null
      receiptFolder.value = null
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
    receiptPeriod.value = null
    receiptFolder.value = null
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
    await uploadVaultFile(uploaded)
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
  receiptFolder.value = 'main'
}

function openCorrectionsFolder(): void {
  receiptFolder.value = 'corrections'
}

function openSalesBooksFolder(): void {
  receiptFolder.value = 'sales_books'
}

function receiptsBack(): void {
  if (receiptFolder.value === 'corrections' || receiptFolder.value === 'sales_books') {
    receiptFolder.value = 'main'
    return
  }
  receiptPeriod.value = null
  receiptFolder.value = null
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
        <NEmpty v-if="!vaultFiles.length && !loading" description="Хранилище пусто" />
        <ul v-else class="file-list">
          <li v-for="file in vaultFiles" :key="file.id" class="file-item">
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
            <template v-if="receiptFolder === 'corrections'"> / Корректировки</template>
            <template v-else-if="receiptFolder === 'sales_books'"> / Книги продаж</template>
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
                <div class="file-meta">
                  {{ period.items.filter((i) => !i.is_correction).length }} основных ·
                  {{ period.items.filter((i) => i.is_correction).length }} корректировок ·
                  {{ periodSalesBooksCount(period) }} книг продаж
                </div>
              </div>
            </div>
            <NButton size="small" secondary @click.stop="openPeriod(period.period_code)">
              Открыть
            </NButton>
          </li>
        </ul>

        <!-- Inside period: main files + subfolders -->
        <template v-else-if="receiptFolder === 'main' || receiptFolder === 'corrections'">
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
              v-if="receiptFolder === 'main' && periodCorrectionItems.length"
              class="file-item file-item--folder"
              @click="openCorrectionsFolder"
            >
              <div class="file-info">
                <FolderOpen :size="16" class="file-icon" />
                <div>
                  <div class="file-name">Корректировки</div>
                  <div class="file-meta">{{ periodCorrectionItems.length }} файл(ов)</div>
                </div>
              </div>
              <NButton size="small" secondary @click.stop="openCorrectionsFolder">Открыть</NButton>
            </li>
            <li
              v-if="receiptFolder === 'main' && periodSalesBookItems.length"
              class="file-item file-item--folder"
              @click="openSalesBooksFolder"
            >
              <div class="file-info">
                <FolderOpen :size="16" class="file-icon" />
                <div>
                  <div class="file-name">Книги продаж</div>
                  <div class="file-meta">{{ periodSalesBookItems.length }} файл(ов)</div>
                </div>
              </div>
              <NButton size="small" secondary @click.stop="openSalesBooksFolder">Открыть</NButton>
            </li>
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
                  <div class="file-meta">
                    {{ receiptKindLabel(row) }} · ИНН {{ row.supplier_inn }}
                    <template v-if="row.supplier_name"> · {{ row.supplier_name }}</template>
                  </div>
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
          <NEmpty
            v-if="
              receiptFolder === 'main' &&
              !periodMainItems.length &&
              !periodCorrectionItems.length &&
              !periodSalesBookItems.length &&
              !loading
            "
            description="В этом периоде пусто"
          />
          <NEmpty
            v-else-if="receiptFolder === 'corrections' && !visibleReceiptItems.length && !loading"
            description="Корректировок нет"
          />
        </template>

        <template v-else-if="receiptFolder === 'sales_books'">
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
                  <div class="file-meta">
                    Продавец {{ row.seller_inn }}
                    <template v-if="row.seller_name"> · {{ row.seller_name }}</template>
                    · Покупатель {{ row.buyer_inn }}
                    <template v-if="row.buyer_name"> · {{ row.buyer_name }}</template>
                  </div>
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
</template>

<style scoped>
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
