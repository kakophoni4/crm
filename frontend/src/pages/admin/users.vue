<script setup lang="ts">
import type { DataTableColumns, SelectOption } from 'naive-ui'
import {
  NButton,
  NCheckbox,
  NDataTable,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NPopconfirm,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import { computed, h, onMounted, ref, watch } from 'vue'

import type { AdminUser, Department, Group } from '@/features/admin/api'
import {
  createUser,
  listDepartments,
  listGroups,
  listUsers,
  resetUserPassword,
  updateUser,
} from '@/features/admin/api'
import {
  adminRemoveUser,
  approveUserDeletionRequest,
  createUserDeletionRequest,
  listUserDeletionRequests,
  rejectUserDeletionRequest,
  type UserDeletionRequest,
} from '@/features/admin/user-deletion-api'
import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'

const message = useMessage()
const auth = useAuthStore()
const isSenior = computed(() => auth.user?.role === 'senior')
const isAdmin = computed(() => auth.user?.role === 'admin')

const loading = ref(false)
const rows = ref<AdminUser[]>([])
const groups = ref<Group[]>([])
const departments = ref<Department[]>([])
const pendingDeletions = ref<UserDeletionRequest[]>([])
const showModal = ref(false)
const editing = ref<AdminUser | null>(null)
const form = ref({
  username: '',
  full_name: '',
  password: '',
  role: 'user' as 'user' | 'senior' | 'admin',
  group_id: null as number | null,
  department_id: null as number | null,
  set_as_department_head: false,
})

const pendingByUserId = computed(() => {
  const map = new Map<number, UserDeletionRequest>()
  for (const req of pendingDeletions.value) {
    if (req.state === 'pending') {
      map.set(req.target_user_id, req)
    }
  }
  return map
})

const roleOptions = computed<SelectOption[]>(() =>
  isSenior.value
    ? [{ label: 'Оператор', value: 'user' }]
    : [
        { label: 'Оператор', value: 'user' },
        { label: 'Старший', value: 'senior' },
        { label: 'Администратор', value: 'admin' },
      ],
)

const groupOptions = computed<SelectOption[]>(() =>
  groups.value.map((g) => {
    const dept = departments.value.find((d) => d.id === g.department_id)
    const suffix = dept ? ` (${dept.name})` : ''
    return { label: `${g.name}${suffix}`, value: g.id }
  }),
)

const departmentOptions = computed<SelectOption[]>(() =>
  departments.value.map((d) => ({ label: d.name, value: d.id })),
)

const showGroupField = computed(() => form.value.role === 'user')
const showDepartmentField = computed(() => form.value.role === 'senior')
const showDepartmentHeadCheckbox = computed(
  () => form.value.role === 'senior' && form.value.department_id != null,
)

function departmentName(id: number | null): string {
  if (id == null) return '—'
  return departments.value.find((d) => d.id === id)?.name ?? '—'
}

function canRequestDeletion(row: AdminUser): boolean {
  if (!isSenior.value) return false
  if (row.id === auth.user?.id) return false
  return row.role === 'user' && row.status === 'active' && !pendingByUserId.value.has(row.id)
}

function canAdminRemove(row: AdminUser): boolean {
  if (!isAdmin.value) return false
  return row.role === 'user' && row.status === 'active'
}

function canAdminApprovePending(row: AdminUser): boolean {
  return isAdmin.value && pendingByUserId.value.has(row.id)
}

const columns = computed<DataTableColumns<AdminUser>>(() => [
  { title: 'Логин', key: 'username', ellipsis: { tooltip: true } },
  { title: 'Имя', key: 'full_name' },
  { title: 'Роль', key: 'role', width: 100 },
  {
    title: 'Отдел',
    key: 'department_id',
    width: 140,
    render: (row) => departmentName(row.department_id),
  },
  {
    title: 'Группа',
    key: 'group_id',
    width: 140,
    render: (row) => groups.value.find((g) => g.id === row.group_id)?.name ?? '—',
  },
  {
    title: 'Статус',
    key: 'status',
    width: 120,
    render: (row) => {
      if (row.status === 'disabled') {
        return h(NTag, { size: 'small', type: 'default', bordered: false }, { default: () => 'отключён' })
      }
      if (pendingByUserId.value.has(row.id)) {
        return h(NTag, { size: 'small', type: 'warning', bordered: false }, { default: () => 'на удалении' })
      }
      return row.status
    },
  },
  {
    title: '',
    key: 'actions',
    width: isAdmin.value ? 320 : 280,
    render: (row) => {
      const buttons: ReturnType<typeof h>[] = [
        h(NButton, { size: 'small', onClick: () => openEdit(row) }, { default: () => 'Изменить' }),
        h(
          NButton,
          { size: 'small', quaternary: true, onClick: () => onResetPassword(row) },
          { default: () => 'Сброс пароля' },
        ),
      ]

      if (canRequestDeletion(row)) {
        buttons.push(
          h(
            NPopconfirm,
            {
              onPositiveClick: () => onRequestDeletion(row),
              positiveText: 'Отправить',
              negativeText: 'Отмена',
            },
            {
              trigger: () =>
                h(
                  NButton,
                  { size: 'small', type: 'error', quaternary: true },
                  { default: () => 'Удалить' },
                ),
              default: () => `Отключить ${row.full_name}? Заявка уйдёт администратору.`,
            },
          ),
        )
      }

      if (canAdminApprovePending(row)) {
        const req = pendingByUserId.value.get(row.id)!
        buttons.push(
          h(
            NButton,
            {
              size: 'small',
              type: 'error',
              onClick: () => onApproveDeletion(req.id),
            },
            { default: () => 'Подтвердить' },
          ),
          h(
            NButton,
            {
              size: 'small',
              quaternary: true,
              onClick: () => onRejectDeletion(req.id),
            },
            { default: () => 'Отклонить' },
          ),
        )
      } else if (canAdminRemove(row) && !canAdminApprovePending(row)) {
        buttons.push(
          h(
            NPopconfirm,
            {
              onPositiveClick: () => onAdminRemove(row),
              positiveText: 'Отключить',
              negativeText: 'Отмена',
            },
            {
              trigger: () =>
                h(
                  NButton,
                  { size: 'small', type: 'error', quaternary: true },
                  { default: () => 'Удалить' },
                ),
              default: () => `Отключить ${row.full_name}?`,
            },
          ),
        )
      }

      return h(NSpace, { size: 4, wrap: true }, () => buttons)
    },
  },
])

function openCreate(): void {
  editing.value = null
  form.value = {
    username: '',
    full_name: '',
    password: '',
    role: 'user',
    group_id: groups.value[0]?.id ?? null,
    department_id: departments.value[0]?.id ?? null,
    set_as_department_head: false,
  }
  showModal.value = true
}

function openEdit(row: AdminUser): void {
  editing.value = row
  const isDeptHead = departments.value.some(
    (d) => d.head_user_id === row.id && d.id === row.department_id,
  )
  form.value = {
    username: row.username,
    full_name: row.full_name,
    password: '',
    role: row.role,
    group_id: row.group_id,
    department_id: row.department_id,
    set_as_department_head: isDeptHead,
  }
  showModal.value = true
}

watch(
  () => form.value.role,
  (role) => {
    if (role === 'admin') {
      form.value.group_id = null
      form.value.department_id = null
      form.value.set_as_department_head = false
    } else if (role === 'senior') {
      form.value.group_id = null
      if (form.value.department_id == null) {
        form.value.department_id = departments.value[0]?.id ?? null
      }
    } else {
      form.value.department_id = null
      form.value.set_as_department_head = false
      if (form.value.group_id == null) {
        form.value.group_id = groups.value[0]?.id ?? null
      }
    }
  },
)

async function loadPendingDeletions(): Promise<void> {
  if (!isSenior.value && !isAdmin.value) {
    pendingDeletions.value = []
    return
  }
  try {
    pendingDeletions.value = await listUserDeletionRequests(
      isAdmin.value ? 'pending' : undefined,
    )
    if (isSenior.value) {
      pendingDeletions.value = pendingDeletions.value.filter((r) => r.state === 'pending')
    }
  } catch {
    pendingDeletions.value = []
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [users, groupList, deptList] = await Promise.all([
      listUsers(),
      listGroups(),
      listDepartments(),
    ])
    rows.value = users
    groups.value = groupList
    departments.value = deptList
    await loadPendingDeletions()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить пользователей')
  } finally {
    loading.value = false
  }
}

function validateForm(role: 'user' | 'senior' | 'admin'): string | null {
  if (!editing.value) {
    if (!form.value.username.trim() || !form.value.password) {
      return 'Заполните логин и пароль'
    }
  }
  if (!form.value.full_name.trim()) {
    return 'Укажите имя'
  }
  if (role === 'user' && form.value.group_id == null) {
    return 'Выберите группу для оператора'
  }
  if (role === 'senior' && form.value.department_id == null) {
    return 'Выберите отдел для старшего'
  }
  return null
}

async function onSave(): Promise<void> {
  const role = isSenior.value ? 'user' : form.value.role
  const validationError = validateForm(role)
  if (validationError) {
    message.warning(validationError)
    return
  }

  try {
    if (editing.value) {
      const patchRole = isSenior.value ? undefined : form.value.role
      await updateUser(editing.value.id, {
        full_name: form.value.full_name.trim(),
        ...(patchRole !== undefined ? { role: patchRole } : {}),
        group_id: form.value.role === 'user' ? form.value.group_id : null,
        department_id: form.value.role === 'senior' ? form.value.department_id : null,
        ...(form.value.role === 'senior' && form.value.set_as_department_head
          ? { set_as_department_head: true }
          : {}),
      })
      message.success('Пользователь обновлён')
    } else {
      await createUser({
        username: form.value.username.trim(),
        full_name: form.value.full_name.trim(),
        password: form.value.password,
        role,
        group_id: role === 'user' ? form.value.group_id : null,
        department_id: role === 'senior' ? form.value.department_id : null,
        set_as_department_head: role === 'senior' && form.value.set_as_department_head,
      })
      message.success('Пользователь создан')
    }
    showModal.value = false
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка сохранения')
  }
}

async function onResetPassword(row: AdminUser): Promise<void> {
  try {
    const { temporary_password } = await resetUserPassword(row.id)
    message.success(`Временный пароль: ${temporary_password}`, { duration: 12000 })
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сбросить пароль')
  }
}

async function onRequestDeletion(row: AdminUser): Promise<void> {
  try {
    await createUserDeletionRequest(row.id)
    message.success('Заявка отправлена администратору')
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось отправить заявку')
  }
}

async function onApproveDeletion(requestId: number): Promise<void> {
  try {
    await approveUserDeletionRequest(requestId)
    message.success('Пользователь отключён, карточки перераспределены')
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось подтвердить удаление')
  }
}

async function onRejectDeletion(requestId: number): Promise<void> {
  try {
    await rejectUserDeletionRequest(requestId)
    message.info('Заявка отклонена')
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось отклонить заявку')
  }
}

async function onAdminRemove(row: AdminUser): Promise<void> {
  try {
    await adminRemoveUser(row.id)
    message.success('Пользователь отключён')
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось удалить пользователя')
  }
}

onMounted(() => void load())
</script>

<template>
  <section class="admin-page">
    <header class="admin-page__header">
      <h1 class="admin-page__title">Пользователи</h1>
      <NButton type="primary" @click="openCreate">Создать пользователя</NButton>
    </header>

    <NSpin :show="loading">
      <NDataTable :columns="columns" :data="rows" :row-key="(r: AdminUser) => r.id" />
    </NSpin>

    <NModal
      v-model:show="showModal"
      preset="card"
      :title="editing ? 'Редактировать пользователя' : 'Новый пользователь'"
      style="max-width: 480px"
    >
      <NForm label-placement="top">
        <NFormItem v-if="!editing" label="Логин">
          <NInput v-model:value="form.username" />
        </NFormItem>
        <NFormItem label="Имя">
          <NInput v-model:value="form.full_name" />
        </NFormItem>
        <NFormItem v-if="!editing" label="Пароль">
          <NInput v-model:value="form.password" type="password" show-password-on="click" />
        </NFormItem>
        <NFormItem v-if="!isSenior" label="Роль">
          <NSelect v-model:value="form.role" :options="roleOptions" />
        </NFormItem>
        <NFormItem v-if="showGroupField" label="Группа">
          <NSelect v-model:value="form.group_id" :options="groupOptions" placeholder="Выбрать" />
        </NFormItem>
        <NFormItem v-if="showDepartmentField" label="Отдел">
          <NSelect
            v-model:value="form.department_id"
            :options="departmentOptions"
            placeholder="Выбрать"
          />
        </NFormItem>
        <NFormItem v-if="showDepartmentHeadCheckbox">
          <NCheckbox v-model:checked="form.set_as_department_head">
            Назначить руководителем отдела
          </NCheckbox>
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
</style>
