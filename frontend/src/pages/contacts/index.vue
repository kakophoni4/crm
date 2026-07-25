<script setup lang="ts">
import { UserPlus } from 'lucide-vue-next'
import type { DataTableColumns, SelectOption } from 'naive-ui'
import {
  NButton,
  NDataTable,
  NIcon,
  NInput,
  NSelect,
  NSpace,
  NSpin,
  useMessage,
} from 'naive-ui'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import type { Contact, ContactStatus } from '@/entities/contact/types'
import { CONTACT_STATUS_FILTER_OPTIONS, contactStatusLabel } from '@/entities/contact/types'
import CreateContactDialog from '@/features/contacts/CreateContactDialog.vue'
import { listContacts } from '@/features/contacts/api'
import { AppError } from '@/shared/api/http'
import {
  invalidateChatsQueries,
  invalidateContactsQueries,
  onContactsInvalidate,
  type ContactsInvalidateEvent,
} from '@/shared/lib/query-invalidation'
import AppCard from '@/shared/ui/AppCard.vue'
import { useAuthStore } from '@/shared/store/auth'

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

const loading = ref(false)
const createDialogVisible = ref(false)
const rows = ref<Contact[]>([])
const total = ref<number | null>(null)
const hasMore = ref(false)
/** Cursor used to fetch the current page; null = first page. */
const pageCursor = ref<string | null>(null)
/** Cursor for the next page (forward). */
const nextCursor = ref<string | null>(null)
const pageSize = ref(20)

const searchQ = ref('')
const statusFilter = ref<ContactStatus | null>(null)

const pageSizeOptions: SelectOption[] = [
  { label: '10', value: 10 },
  { label: '20', value: 20 },
  { label: '50', value: 50 },
]

const showContactPrivateFields = computed(
  () =>
    auth.user?.role === 'admin' ||
    auth.user?.role === 'senior' ||
    auth.user?.role === 'group_senior',
)

const showTelegramUserId = computed(() => auth.isAdmin)

const canCreateContact = computed(
  () => auth.user?.permissions.includes('contacts.create') === true,
)

const isFirstPage = computed(() => pageCursor.value == null)

const rangeText = computed(() => {
  if (!rows.value.length) return 'Нет записей'
  if (total.value != null) return `Показано ${rows.value.length} из ${total.value}`
  if (isFirstPage.value) {
    const to = rows.value.length
    return hasMore.value ? `Показано 1–${to}+` : `Показано 1–${to}`
  }
  return hasMore.value
    ? `Показано ${rows.value.length}+`
    : `Показано ${rows.value.length}`
})

function onContactCreated(contact: Contact): void {
  invalidateContactsQueries({ immediate: true })
  invalidateChatsQueries({ immediate: true })
  const chatId = contact.workspace?.chat_id
  if (chatId != null) {
    void router.push({ name: 'chats', query: { chatId: String(chatId) } })
    return
  }
  void router.push({ name: 'contact-detail', params: { id: contact.id } })
}

const columns = computed<DataTableColumns<Contact>>(() => {
  const base: DataTableColumns<Contact> = [
    {
      title: 'Имя',
      key: 'full_name',
      minWidth: 160,
      ellipsis: { tooltip: true },
    },
    {
      title: 'Пометка',
      key: 'note',
      minWidth: 160,
      ellipsis: { tooltip: true },
      render: (row) => row.note?.trim() || '—',
    },
  ]

  if (showContactPrivateFields.value) {
    base.push(
      {
        title: 'Телефон',
        key: 'phone',
        minWidth: 130,
        render: (row) => row.phone ?? '—',
      },
      {
        title: 'Email',
        key: 'email',
        minWidth: 160,
        ellipsis: { tooltip: true },
        render: (row) => row.email ?? '—',
      },
      {
        title: 'Telegram',
        key: 'telegram_username',
        minWidth: 130,
        render: (row) => row.telegram_username ?? '—',
      },
    )
  }

  base.push({
    title: 'Статус',
    key: 'status',
    width: 120,
    render: (row) => contactStatusLabel(row.status),
  })

  if (showTelegramUserId.value) {
    base.push({
      title: 'TG user ID',
      key: 'telegram_user_id',
      width: 120,
      render: (row) =>
        row.telegram_user_id != null ? String(row.telegram_user_id) : '—',
    })
  }

  return base
})

function openContact(row: Contact): void {
  void router.push({ name: 'contact-detail', params: { id: row.id } })
}

function rowProps(row: Contact): Record<string, unknown> {
  return {
    style: 'cursor: pointer',
    onClick: () => openContact(row),
  }
}

/** Bumps on each fetchPage(); stale list responses are ignored. */
let listFetchSeq = 0

function isRequestCanceled(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false
  const code = (err as { code?: string }).code
  return code === 'ERR_CANCELED' || code === 'ECONNABORTED'
}

function applyContactPatch(event: ContactsInvalidateEvent): void {
  const patchEvent = event.patch
  if (!patchEvent) return
  const idx = rows.value.findIndex((row) => row.id === patchEvent.contactId)
  if (idx < 0) return
  const next = rows.value.slice()
  next[idx] = { ...next[idx], ...patchEvent.patch }
  rows.value = next
}

function resetCursorState(): void {
  pageCursor.value = null
  nextCursor.value = null
  hasMore.value = false
  total.value = null
}

async function fetchPage(opts?: {
  silent?: boolean
  /** Override cursor for this fetch; omit to reload current page. */
  cursor?: string | null
}): Promise<void> {
  const silent = opts?.silent === true && rows.value.length > 0
  const seq = ++listFetchSeq
  const cursor = opts?.cursor !== undefined ? opts.cursor : pageCursor.value
  if (!silent) loading.value = true
  try {
    const data = await listContacts({
      q: searchQ.value.trim() || undefined,
      status: statusFilter.value ?? undefined,
      limit: pageSize.value,
      ...(cursor ? { cursor } : {}),
    })
    if (seq !== listFetchSeq) return

    if (data.items.length === 0 && cursor) {
      resetCursorState()
      void fetchPage(opts)
      return
    }

    pageCursor.value = cursor
    nextCursor.value = data.next_cursor
    hasMore.value = data.has_more
    if (data.total != null) total.value = data.total
    rows.value = data.items
  } catch (err) {
    if (seq !== listFetchSeq || isRequestCanceled(err)) return
    const text = err instanceof AppError ? err.message : 'Не удалось загрузить контакты'
    message.error(text)
  } finally {
    if (seq === listFetchSeq) loading.value = false
  }
}

function applyFilters(): void {
  resetCursorState()
  void fetchPage({ cursor: null })
}

function loadNext(): void {
  if (!nextCursor.value || loading.value) return
  void fetchPage({ cursor: nextCursor.value })
}

function loadFirst(): void {
  if (isFirstPage.value || loading.value) return
  resetCursorState()
  void fetchPage({ cursor: null })
}

function onPageSizeChange(size: number): void {
  pageSize.value = size
  resetCursorState()
  void fetchPage({ cursor: null })
}

let stopInvalidate: (() => void) | undefined

onMounted(() => {
  void fetchPage({ cursor: null })
  stopInvalidate = onContactsInvalidate((event) => {
    if (event.patch) applyContactPatch(event)
    if (event.reload) void fetchPage({ silent: true })
  })
})

onUnmounted(() => {
  stopInvalidate?.()
})

watch(
  () => auth.user?.role,
  () => {
    void fetchPage()
  },
)
</script>

<template>
  <section class="contacts-page">
    <header class="contacts-page__header">
      <h1 class="contacts-page__title">Контакты</h1>
      <NButton
        v-if="canCreateContact"
        type="primary"
        @click="createDialogVisible = true"
      >
        <template #icon>
          <NIcon><UserPlus /></NIcon>
        </template>
        Создать контакт
      </NButton>
    </header>

    <AppCard class="contacts-page__panel">
      <NSpace class="contacts-page__filters" wrap :size="12" align="center" justify="center">
        <NInput
          v-model:value="searchQ"
          clearable
          placeholder="Поиск"
          class="contacts-page__field contacts-page__field--search"
          @keyup.enter="applyFilters"
        />
        <NSelect
          v-model:value="statusFilter"
          :options="CONTACT_STATUS_FILTER_OPTIONS"
          placeholder="Статус"
          clearable
          class="contacts-page__field contacts-page__field--status"
        />
        <NButton type="primary" :loading="loading" @click="applyFilters">Применить</NButton>
      </NSpace>

      <NSpin :show="loading" class="contacts-page__spin">
        <div class="contacts-page__table-wrap">
          <NDataTable
            class="contacts-page__table"
            :columns="columns"
            :data="rows"
            :remote="true"
            :row-key="(row: Contact) => row.id"
            :row-props="rowProps"
            :bordered="false"
            :single-line="false"
            striped
            size="small"
          />
        </div>
        <div class="contacts-page__pager">
          <span class="contacts-page__range">{{ rangeText }}</span>
          <NSpace :size="8" align="center" wrap>
            <NSelect
              :value="pageSize"
              :options="pageSizeOptions"
              size="small"
              class="contacts-page__page-size"
              :disabled="loading"
              @update:value="onPageSizeChange"
            />
            <NButton
              size="small"
              :disabled="isFirstPage || loading"
              @click="loadFirst"
            >
              В начало
            </NButton>
            <NButton
              size="small"
              type="primary"
              :disabled="!hasMore || !nextCursor || loading"
              @click="loadNext"
            >
              Далее
            </NButton>
          </NSpace>
        </div>
      </NSpin>
    </AppCard>

    <CreateContactDialog
      v-model:show="createDialogVisible"
      source="manual"
      @created="onContactCreated"
    />
  </section>
</template>

<style scoped>
.contacts-page {
  width: min(1120px, 100%);
  margin: 0 auto;
  padding-bottom: 16px;
  box-sizing: border-box;
}

.contacts-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.contacts-page__title {
  margin: 0;
  font-size: clamp(1.375rem, 2vw, 1.5rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.contacts-page__panel :deep(.app-card__body) {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.contacts-page__filters {
  flex-wrap: wrap;
  width: 100%;
}

.contacts-page__field--search {
  width: min(100%, 280px);
}

.contacts-page__field--status {
  width: min(100%, 200px);
}

.contacts-page__spin {
  display: block;
  min-width: 0;
}

.contacts-page__spin :deep(.n-spin-content) {
  min-width: 0;
}

.contacts-page__table-wrap {
  width: 100%;
  min-width: 0;
  overflow-x: auto;
}

.contacts-page__table-wrap :deep(.n-data-table-wrapper) {
  width: 100%;
  min-width: 0;
}

.contacts-page__table-wrap :deep(.n-data-table-base-table) {
  width: 100%;
}

.contacts-page__table-wrap :deep(.n-data-table-empty) {
  flex: 1;
  min-height: min(42vh, 320px);
  box-sizing: border-box;
}

.contacts-page__pager {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 12px;
}

.contacts-page__range {
  color: var(--n-text-color-3, var(--app-muted, #888));
  font-size: 13px;
}

.contacts-page__page-size {
  width: 72px;
}

.contacts-page__table :deep(.n-data-table-tr:hover) {
  background-color: color-mix(in srgb, var(--app-text) 4%, transparent);
}
</style>
