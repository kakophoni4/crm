<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import {
  NButton,
  NDataTable,
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
import { listContacts } from '@/features/contacts/api'
import { AppError } from '@/shared/api/http'
import { onContactsInvalidate } from '@/shared/lib/query-invalidation'
import AppCard from '@/shared/ui/AppCard.vue'
import { useAuthStore } from '@/shared/store/auth'

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

const loading = ref(false)
const rows = ref<Contact[]>([])
const nextCursor = ref<string | null>(null)
const cursorStack = ref<(string | undefined)[]>([undefined])
const pageIndex = ref(1)
const pageSize = ref(20)

const searchQ = ref('')
const statusFilter = ref<ContactStatus | null>(null)

const showContactPrivateFields = computed(
  () => auth.user?.role === 'admin' || auth.user?.role === 'senior',
)

const showTelegramUserId = computed(() => auth.isAdmin)

const columns = computed<DataTableColumns<Contact>>(() => {
  const base: DataTableColumns<Contact> = [
    {
      title: 'Имя',
      key: 'full_name',
      width: 180,
      ellipsis: { tooltip: true },
    },
    {
      title: 'Пометка',
      key: 'note',
      width: 200,
      ellipsis: { tooltip: true },
      render: (row) => row.note?.trim() || '—',
    },
  ]

  if (showContactPrivateFields.value) {
    base.push(
      {
        title: 'Телефон',
        key: 'phone',
        width: 140,
        render: (row) => row.phone ?? '—',
      },
      {
        title: 'Email',
        key: 'email',
        width: 180,
        ellipsis: { tooltip: true },
        render: (row) => row.email ?? '—',
      },
      {
        title: 'Telegram',
        key: 'telegram_username',
        width: 140,
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

const pagination = computed(() => ({
  page: pageIndex.value,
  pageSize: pageSize.value,
  itemCount: rows.value.length + (nextCursor.value ? pageSize.value : 0),
  pageSlot: 5,
  showSizePicker: true,
  pageSizes: [10, 20, 50],
  prefix: () => `Страница ${pageIndex.value}`,
}))

function currentCursor(): string | undefined {
  return cursorStack.value[pageIndex.value - 1]
}

async function fetchPage(): Promise<void> {
  loading.value = true
  try {
    const data = await listContacts({
      q: searchQ.value.trim() || undefined,
      status: statusFilter.value ?? undefined,
      cursor: currentCursor(),
      limit: pageSize.value,
    })
    rows.value = data.items
    nextCursor.value = data.next_cursor
  } catch (err) {
    const text = err instanceof AppError ? err.message : 'Не удалось загрузить контакты'
    message.error(text)
  } finally {
    loading.value = false
  }
}

function resetPagination(): void {
  pageIndex.value = 1
  cursorStack.value = [undefined]
  nextCursor.value = null
}

function applyFilters(): void {
  resetPagination()
  void fetchPage()
}

function onPageChange(page: number): void {
  if (page > pageIndex.value) {
    if (!nextCursor.value) return
    if (cursorStack.value.length < page) {
      cursorStack.value.push(nextCursor.value)
    }
  } else if (page < pageIndex.value) {
    cursorStack.value = cursorStack.value.slice(0, page)
  }
  pageIndex.value = page
  void fetchPage()
}

function onPageSizeChange(size: number): void {
  pageSize.value = size
  applyFilters()
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
    </header>

    <AppCard class="contacts-page__panel">
      <NSpace class="contacts-page__filters" wrap :size="12" align="center">
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
  </section>
</template>

<style scoped>
.contacts-page {
  max-width: 1280px;
  margin: 0 auto;
  padding: 8px clamp(12px, 2.5vw, 24px) 40px;
  box-sizing: border-box;
}

.contacts-page__header {
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

/* Было width: fit-content — из‑за этого пустая таблица сжималась в «узкую полоску». */
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
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.contacts-page__table :deep(.n-data-table-tr:hover) {
  background-color: rgba(255, 255, 255, 0.04);
}
</style>
