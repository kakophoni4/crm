<script setup lang="ts">
import type { DataTableColumns, SelectOption } from 'naive-ui'
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
import { computed, h, onMounted, ref, watch } from 'vue'

import type { Department, Group } from '@/features/admin/api'
import {
  createGroup,
  deleteGroup,
  listDepartments,
  listGroups,
  updateGroup,
} from '@/features/admin/api'
import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'

const message = useMessage()
const auth = useAuthStore()
const isSenior = computed(() => auth.user?.role === 'senior')
const loading = ref(false)
const rows = ref<Group[]>([])
const departments = ref<Department[]>([])
const filterDeptId = ref<number | null>(null)
const showModal = ref(false)
const editing = ref<Group | null>(null)
const form = ref({ name: '', department_id: null as number | null })

const deptOptions = computed<SelectOption[]>(() =>
  departments.value.map((d) => ({ label: d.name, value: d.id })),
)

const listDeptFilter = computed(() => {
  if (isSenior.value && auth.user?.department_id != null) return auth.user.department_id
  return filterDeptId.value ?? undefined
})

const columns = computed<DataTableColumns<Group>>(() => [
  { title: 'Название', key: 'name' },
  {
    title: 'Отдел',
    key: 'department_id',
    width: 160,
    render: (row) =>
      departments.value.find((d) => d.id === row.department_id)?.name ??
      String(row.department_id),
  },
  {
    title: '',
    key: 'actions',
    width: 180,
    render: (row) =>
      h(NSpace, null, () => [
        h(NButton, { size: 'small', onClick: () => openEdit(row) }, { default: () => 'Изменить' }),
        h(
          NButton,
          { size: 'small', type: 'error', quaternary: true, onClick: () => onDelete(row) },
          { default: () => 'Удалить' },
        ),
      ]),
  },
])

function openCreate(): void {
  editing.value = null
  form.value = {
    name: '',
    department_id:
      (isSenior.value ? auth.user?.department_id : null) ??
      filterDeptId.value ??
      departments.value[0]?.id ??
      null,
  }
  showModal.value = true
}

function openEdit(row: Group): void {
  editing.value = row
  form.value = { name: row.name, department_id: row.department_id }
  showModal.value = true
}

async function loadDepartments(): Promise<void> {
  departments.value = await listDepartments()
}

async function load(): Promise<void> {
  loading.value = true
  try {
    rows.value = await listGroups(listDeptFilter.value)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить группы')
  } finally {
    loading.value = false
  }
}

async function onSave(): Promise<void> {
  const deptId =
    isSenior.value && auth.user?.department_id != null
      ? auth.user.department_id
      : form.value.department_id
  if (!form.value.name.trim() || deptId == null) {
    message.warning('Заполните название и отдел')
    return
  }
  try {
    if (editing.value) {
      await updateGroup(editing.value.id, { name: form.value.name.trim() })
      message.success('Группа обновлена')
    } else {
      await createGroup({
        name: form.value.name.trim(),
        department_id: deptId,
      })
      message.success('Группа создана')
    }
    showModal.value = false
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка сохранения')
  }
}

async function onDelete(row: Group): Promise<void> {
  try {
    await deleteGroup(row.id)
    message.success('Группа удалена')
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось удалить')
  }
}

watch([filterDeptId, isSenior], () => void load())

onMounted(async () => {
  try {
    await loadDepartments()
    if (isSenior.value && auth.user?.department_id != null) {
      filterDeptId.value = auth.user.department_id
    }
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка загрузки')
  }
})
</script>

<template>
  <section class="admin-page">
    <header class="admin-page__header">
      <h1 class="admin-page__title">Группы</h1>
      <NSpace>
        <NSelect
          v-if="!isSenior"
          v-model:value="filterDeptId"
          :options="deptOptions"
          placeholder="Все отделы"
          clearable
          style="width: 220px"
        />
        <NButton type="primary" @click="openCreate">Создать группу</NButton>
      </NSpace>
    </header>
    <NSpin :show="loading">
      <NDataTable :columns="columns" :data="rows" :row-key="(r: Group) => r.id" />
    </NSpin>

    <NModal
      v-model:show="showModal"
      preset="card"
      :title="editing ? 'Редактировать группу' : 'Новая группа'"
      style="max-width: 420px"
    >
      <NForm label-placement="top">
        <NFormItem label="Название">
          <NInput v-model:value="form.name" />
        </NFormItem>
        <NFormItem v-if="!editing && !isSenior" label="Отдел">
          <NSelect v-model:value="form.department_id" :options="deptOptions" />
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
  flex-wrap: wrap;
}

.admin-page__title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}
</style>
