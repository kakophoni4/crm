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
import { Copy, Link2, Trash2, Upload } from 'lucide-vue-next'
import { computed, h, onMounted, ref } from 'vue'

import {
  createVaultShareLink,
  deleteVaultFile,
  downloadGroupFile,
  listGroupFileGroups,
  listGroupFiles,
  listVaultFiles,
  revokeShareLink,
  uploadVaultFile,
  type GroupChatFile,
  type VaultFile,
} from '@/features/storage/api'
import { AppError } from '@/shared/api/http'
import { formatFileSize, maxUploadBytesFor, uploadLimitLabel } from '@/shared/config/uploads'
import { resolveAttachmentPreviewKind } from '@/shared/lib/attachment-preview-kind'
import AppCard from '@/shared/ui/AppCard.vue'

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
const previewName = ref('')
const previewOpen = ref(false)

const previewKind = computed(() =>
  previewName.value
    ? resolveAttachmentPreviewKind({ name: previewName.value, mime: '' })
    : 'unsupported',
)

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
    const data = await listGroupFiles({ group_id: selectedGroupId.value, limit: 200 })
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

async function previewGroupFile(row: GroupChatFile): Promise<void> {
  try {
    const blob = await downloadGroupFile(row.id)
    if (previewBlobUrl.value) URL.revokeObjectURL(previewBlobUrl.value)
    previewBlobUrl.value = URL.createObjectURL(blob)
    previewName.value = row.original_name
    previewOpen.value = true
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось открыть файл')
  }
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
    width: 180,
    render: (row) =>
      h(NSpace, { size: 4 }, () => [
        h(
          NButton,
          { size: 'small', quaternary: true, onClick: () => openShareModal(row) },
          { icon: () => h(Link2, { size: 14 }), default: () => 'Ссылка' },
        ),
        h(
          NButton,
          { size: 'small', quaternary: true, type: 'error', onClick: () => onDeleteVault(row) },
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
    width: 160,
    render: (row) =>
      row.direction === 'inbound'
        ? `Клиент: ${row.sender_display_name}`
        : `Оператор: ${row.sender_display_name}`,
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
              <NDataTable :columns="vaultColumns" :data="vaultFiles" :bordered="false" />
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

    <NModal v-model:show="previewOpen" preset="card" :title="previewName" style="width: 80vw">
      <img
        v-if="previewBlobUrl && previewKind === 'image'"
        :src="previewBlobUrl"
        class="preview-img"
        :alt="previewName"
      />
      <iframe
        v-else-if="previewBlobUrl && previewKind === 'pdf'"
        :src="previewBlobUrl"
        class="preview-frame"
      />
      <p v-else>Предпросмотр недоступен — скачайте файл из чата.</p>
    </NModal>
  </div>
</template>

<style scoped>
.storage-page {
  padding: 16px;
  max-width: 1200px;
  margin: 0 auto;
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
  color: var(--n-text-color-3);
}

.hint,
.empty-hint {
  color: var(--n-text-color-3);
  font-size: 13px;
}

.preview-img {
  max-width: 100%;
  max-height: 70vh;
  display: block;
  margin: 0 auto;
}

.preview-frame {
  width: 100%;
  height: 70vh;
  border: none;
}
</style>
