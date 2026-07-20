<script setup lang="ts">
import { UserPlus } from 'lucide-vue-next'
import type { DataTableColumns } from 'naive-ui'
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
import { invalidateChatsQueries, invalidateContactsQueries, onContactsInvalidate } from '@/shared/lib/query-invalidation'
import AppCard from '@/shared/ui/AppCard.vue'
import { useAuthStore } from '@/shared/store/auth'

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

const loading = ref(false)
const createDialogVisible = ref(false)
const rows = ref<Contact[]>([])
const total = ref(0)
const pageIndex = ref(1)
const pageSize = ref(20)

const searchQ = ref('')
const statusFilter = ref<ContactStatus | null>(null)

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

function onContactCreated(contact: Contact): void {
  invalidateContactsQueries()
  invalidateChatsQueries()
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

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value) || 1))

const pagination = computed(() => ({
  page: pageIndex.value,
  pageSize: pageSize.value,
  itemCount: total.value,
  pageCount: pageCount.value,
  /** Sliding window around current page; first & last stay visible via Naive ellipsis. */
  pageSlot: 7,
  showSizePicker: true,
  pageSizes: [10, 20, 50],
  showQuickJumper: pageCount.value > 7,
  prefix: ({ itemCount }: { itemCount: number | undefined }) =>
    `Всего ${itemCount ?? total.value}`,
}))

async function fetchPage(): Promise<void> {
  loading.value = true
  try {
    let page = pageIndex.value
    const data = await listContacts({
      q: searchQ.value.trim() || undefined,
      status: statusFilter.value ?? undefined,
      offset: (page - 1) * pageSize.value,
      limit: pageSize.value,
    })
    total.value = data.total ?? 0
    const maxPage = Math.max(1, Math.ceil(total.value / pageSize.value) || 1)
    if (page > maxPage) {
      page = maxPage
      pageIndex.value = maxPage
      const again = await listContacts({
        q: searchQ.value.trim() || undefined,
        status: statusFilter.value ?? undefined,
        offset: (page - 1) * pageSize.value,
        limit: pageSize.value,
      })
      rows.value = again.items
      total.value = again.total ?? 0
    } else {
      rows.value = data.items
    }
  } catch (err) {
    const text = err instanceof AppError ? err.message : 'Не удалось загрузить контакты'
    message.error(text)
  } finally {
    loading.value = false
  }
}

function applyFilters(): void {
  pageIndex.value = 1
  void fetchPage()
}

function onPageChange(page: number): void {
  if (page < 1 || page > pageCount.value || page === pageIndex.value) return
  pageIndex.value = page
  void fetchPage()
}

function onPageSizeChange(size: number): void {
  pageSize.value = size
  pageIndex.value = 1
  void fetchPage()
}

let stopInvalidate: (() => void) | undefined

onMounted(() => {
  void fetchPage()
  stopInvalidate = onContactsInvalidate(() => {
    void fetchPage()
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
            :pagination="pagination"
            :row-key="(row: Contact) => row.id"
            :row-props="rowProps"
            :bordered="false"
            :single-line="false"
            striped
            size="small"
            @update:page="onPageChange"
            @update:page-size="onPageSizeChange"
          />
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

.contacts-page__table-wrap :deep(.n-data-table-pagination) {
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
}

.contacts-page__table :deep(.n-data-table-tr:hover) {
  background-color: color-mix(in srgb, var(--app-text) 4%, transparent);
}
</style>
