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
import { Copy, Download, Eye, Link2, Pencil, Trash2, Upload } from 'lucide-vue-next'
import { computed, h, onMounted, ref } from 'vue'

import {
  createVaultShareLink,
  deleteVaultFile,
  downloadGroupFile,
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

const message = useMessage()
const activeTab = ref('vault')
const loading = ref(false)

const vaultFiles = ref<VaultFile[]>([])
const groupSummaries = ref<{ group_id: number; group_name: string; file_count: number }[]>([])
const groupFiles = ref<GroupChatFile[]>([])
const selectedGroupId = ref<number | null>(null)

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
  loading.value = true
  try {
    const data = await listVaultFiles({ limit: 100 })
    vaultFiles.value = data.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить файлы')
  } finally {
    loading.value = false
  }
}

async function loadGroupSummaries(): Promise<void> {
  try {
    const data = await listGroupFileGroups()
    groupSummaries.value = data.items
    if (!selectedGroupId.value && data.items.length > 0) {
      selectedGroupId.value = data.items[0].group_id
      await loadGroupFiles()
    }
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить группы')
  }
}

async function loadGroupFiles(): Promise<void> {
  if (selectedGroupId.value == null) {
    groupFiles.value = []
    return
  }
  loading.value = true
  try {
    const data = await listGroupFiles({ group_id: selectedGroupId.value, limit: 100 })
    groupFiles.value = data.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить файлы чатов')
  } finally {
    loading.value = false
  }
}

async function onVaultUpload(data: { file: UploadFileInfo }): Promise<boolean> {
  const file = data.file.file
  if (!file) return false
  if (file.size > maxUploadBytesFor(file)) {
    message.error(`Файл слишком большой (макс. ${uploadLimitLabel(file)})`)
    return false
  }
  try {
    await uploadVaultFile(file)
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
    message.success('Файл удалён')
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
  shareTarget.value = row
  shareExpiresHours.value = 168
  shareMaxDownloads.value = null
  sharePassword.value = ''
  shareModalOpen.value = true
}

async function submitShare(): Promise<void> {
  if (!shareTarget.value) return
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

const groupFilesByChat = computed(() => {
  const map = new Map<number, { chatLabel: string; files: GroupChatFile[] }>()
  for (const file of groupFiles.value) {
    const label = file.contact_name
      ? `${file.contact_name} (чат #${file.chat_id})`
      : `Чат #${file.chat_id}`
    const bucket = map.get(file.chat_id)
    if (bucket) {
      bucket.files.push(file)
    } else {
      map.set(file.chat_id, { chatLabel: label, files: [file] })
    }
  }
  return [...map.values()]
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

onMounted(async () => {
  await loadVault()
  await loadGroupSummaries()
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
            <NUpload :show-file-list="false" @before-upload="onVaultUpload">
              <NButton type="primary">
                <template #icon><Upload :size="16" /></template>
                Загрузить файл
              </NButton>
            </NUpload>
            <NSpin :show="loading">
              <NDataTable
                :columns="vaultColumns"
                :data="vaultFiles"
                :bordered="false"
                virtual-scroll
                :max-height="VIRTUAL_DATA_TABLE_MAX_HEIGHT"
                :min-row-height="VIRTUAL_DATA_TABLE_MIN_ROW_HEIGHT"
              />
            </NSpin>
            <div v-for="file in vaultFiles" :key="file.id" class="share-list">
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

        <NTabPane name="group" tab="Файлы из чатов">
          <NSpace vertical :size="16">
            <NSpace>
              <NButton
                v-for="g in groupSummaries"
                :key="g.group_id"
                :type="selectedGroupId === g.group_id ? 'primary' : 'default'"
                size="small"
                @click="
                  () => {
                    selectedGroupId = g.group_id
                    void loadGroupFiles()
                  }
                "
              >
                {{ g.group_name }} ({{ g.file_count }})
              </NButton>
            </NSpace>
            <NSpin :show="loading">
              <div v-for="chat in groupFilesByChat" :key="chat.chatLabel" class="chat-block">
                <h3 class="chat-block-title">{{ chat.chatLabel }}</h3>
                <NDataTable
                  :columns="groupColumns"
                  :data="chat.files"
                  :bordered="false"
                  size="small"
                  virtual-scroll
                  :max-height="480"
                  :min-row-height="VIRTUAL_DATA_TABLE_MIN_ROW_HEIGHT"
                />
              </div>
              <p v-if="!groupFilesByChat.length && !loading" class="empty-hint">
                В выбранной группе пока нет файлов из чатов
              </p>
            </NSpin>
          </NSpace>
        </NTabPane>
      </NTabs>
    </AppCard>

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
</style>
