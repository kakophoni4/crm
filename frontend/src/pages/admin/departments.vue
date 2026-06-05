<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import {
  NButton,
  NDataTable,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  useMessage,
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'

import type { AdminUser, Department } from '@/features/admin/api'
import {
  createDepartment,
  deleteDepartment,
  listDepartments,
  listUsers,
  updateDepartment,
} from '@/features/admin/api'
import { AppError } from '@/shared/api/http'

const message = useMessage()
const loading = ref(false)
const rows = ref<Department[]>([])
const users = ref<AdminUser[]>([])
const showModal = ref(false)
const editing = ref<Department | null>(null)
const form = ref({ name: '', head_user_id: null as number | null })

const headUserOptions = computed(() =>
  users.value.map((u) => ({ label: u.full_name, value: u.id })),
)

const columns = computed<DataTableColumns<Department>>(() => [
  { title: 'Название', key: 'name' },
  {
    title: 'Руководитель',
    key: 'head_user_id',
    width: 180,
    render: (row) =>
      users.value.find((u) => u.id === row.head_user_id)?.full_name ?? '—',
  },
  {
    title: '',
    key: 'actions',
    width: 180,
    render: (row) =>
      h(NSpace, null, () => [
        h(
          NButton,
          { size: 'small', onClick: () => openEdit(row) },
          { default: () => 'Изменить' },
        ),
        h(
          NButton,
          { size: 'small', type: 'error', quaternary: true, onClick: () => onDelete(row) },
          { default: () => 'Удалить' },
        ),
      ]),
  },
])

async function ensureUsers(): Promise<void> {
  if (users.value.length > 0) return
  try {
    users.value = await listUsers()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить пользователей')
  }
}

async function openCreate(): Promise<void> {
  await ensureUsers()
  editing.value = null
  form.value = { name: '', head_user_id: null }
  showModal.value = true
}

async function openEdit(row: Department): Promise<void> {
  await ensureUsers()
  editing.value = row
  form.value = { name: row.name, head_user_id: row.head_user_id }
  showModal.value = true
}

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await listDepartments()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить отделы')
  } finally {
    loading.value = false
  }
}

async function onSave(): Promise<void> {
  if (!form.value.name.trim()) {
    message.warning('Укажите название')
    return
  }
  try {
    if (editing.value) {
      await updateDepartment(editing.value.id, {
        name: form.value.name.trim(),
        head_user_id: form.value.head_user_id,
      })
      message.success('Отдел обновлён')
    } else {
      await createDepartment({
        name: form.value.name.trim(),
        head_user_id: form.value.head_user_id,
      })
      message.success('Отдел создан')
    }
    showModal.value = false
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка сохранения')
  }
}

async function onDelete(row: Department): Promise<void> {
  try {
    await deleteDepartment(row.id)
    message.success('Отдел удалён')
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось удалить')
  }
}

onMounted(async () => {
  try {
    users.value = await listUsers()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить пользователей')
  }
  await load()
})
</script>

<template>
  <section class="admin-page">
    <header class="admin-page__header">
      <h1 class="admin-page__title">Отделы</h1>
      <NButton type="primary" @click="openCreate">Создать отдел</NButton>
    </header>
    <NSpin :show="loading">
      <NDataTable :columns="columns" :data="rows" :row-key="(r: Department) => r.id" />
    </NSpin>

    <NModal
      v-model:show="showModal"
      preset="card"
      :title="editing ? 'Редактировать отдел' : 'Новый отдел'"
      style="max-width: 420px"
    >
      <NForm label-placement="top">
        <NFormItem label="Название">
          <NInput v-model:value="form.name" />
        </NFormItem>
        <NFormItem label="Руководитель (необязательно)">
          <NSelect
            v-model:value="form.head_user_id"
            :options="headUserOptions"
            clearable
            placeholder="Не назначен"
            class="w-full"
          />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showModal = false">Отмена</NButton>
          <NButton type="primary" @click="onSave">Сохранить</NButton>
        </NSpace>
      </template>
    </NModal>
  </section>
</template>

<style scoped>
.admin-page__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
}

.admin-page__title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}

.w-full {
  width: 100%;
}
</style>
