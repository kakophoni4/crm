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
const isGroupSenior = computed(() => auth.user?.role === 'group_senior')
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
  role: 'user' as
    | 'user'
    | 'senior'
    | 'group_senior'
    | 'admin'
    | 'accountant'
    | 'chief_accountant',
  group_ids: [] as number[],
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
        { label: 'Бухгалтер', value: 'accountant' },
        { label: 'Главный бухгалтер', value: 'chief_accountant' },
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

const showGroupField = computed(
  () => form.value.role === 'user' || form.value.role === 'group_senior',
)
const showDepartmentField = computed(() => form.value.role === 'senior')
const showDepartmentHeadCheckbox = computed(
  () => form.value.role === 'senior' && form.value.department_id != null,
)
const showRoleSelect = computed(
  () => !isSenior.value && !(editing.value != null && form.value.role === 'group_senior'),
)
const canToggleGroupSenior = computed(() => {
  if (!editing.value) return false
  if (!isAdmin.value && !isSenior.value && !isGroupSenior.value) return false
  return form.value.role === 'user' || form.value.role === 'group_senior'
})
const promotingGroupSenior = ref(false)

function departmentName(id: number | null): string {
  if (id == null) return '—'
  return departments.value.find((d) => d.id === id)?.name ?? '—'
}

function roleLabel(role: AdminUser['role']): string {
  switch (role) {
    case 'user':
      return 'Оператор'
    case 'group_senior':
      return 'Старший группы'
    case 'senior':
      return 'Старший'
    case 'accountant':
      return 'Бухгалтер'
    case 'chief_accountant':
      return 'Главный бухгалтер'
    case 'admin':
      return 'Администратор'
    default:
      return role
  }
}

function canRequestDeletion(row: AdminUser): boolean {
  if (!isSenior.value && !isGroupSenior.value) return false
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
  { title: 'Роль', key: 'role', width: 140, render: (row) => roleLabel(row.role) },
  {
    title: 'Отдел',
    key: 'department_id',
    width: 140,
    render: (row) => departmentName(row.department_id),
  },
  {
    title: 'Группы',
    key: 'group_ids',
    width: 180,
    render: (row) => {
      const ids = row.group_ids?.length ? row.group_ids : row.group_id != null ? [row.group_id] : []
      if (!ids.length) return '—'
      return ids
        .map((id) => groups.value.find((g) => g.id === id)?.name ?? `#${id}`)
        .join(', ')
    },
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
    group_ids: groups.value[0] ? [groups.value[0].id] : [],
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
    group_ids:
      row.group_ids?.length > 0
        ? [...row.group_ids]
        : row.group_id != null
          ? [row.group_id]
          : [],
    department_id: row.department_id,
    set_as_department_head: isDeptHead,
  }
  showModal.value = true
}

watch(
  () => form.value.role,
  (role) => {
    if (role === 'admin' || role === 'accountant' || role === 'chief_accountant') {
      form.value.group_ids = []
      form.value.department_id = null
      form.value.set_as_department_head = false
    } else if (role === 'senior') {
      form.value.group_ids = []
      form.value.set_as_department_head = false
      if (form.value.department_id == null) {
        form.value.department_id = departments.value[0]?.id ?? null
      }
    } else {
      // user | group_senior
      form.value.department_id = null
      form.value.set_as_department_head = false
      if (form.value.group_ids.length === 0) {
        form.value.group_ids = groups.value[0] ? [groups.value[0].id] : []
      }
    }
  },
)

async function loadPendingDeletions(): Promise<void> {
  if (!isSenior.value && !isGroupSenior.value && !isAdmin.value) {
    pendingDeletions.value = []
    return
  }
  try {
    pendingDeletions.value = await listUserDeletionRequests(
      isAdmin.value ? 'pending' : undefined,
    )
    if (isSenior.value || isGroupSenior.value) {
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

function validateForm(
  role: 'user' | 'senior' | 'group_senior' | 'admin' | 'accountant' | 'chief_accountant',
): string | null {
  if (!editing.value) {
    if (!form.value.username.trim() || !form.value.password) {
      return 'Заполните логин и пароль'
    }
  }
  if (!form.value.full_name.trim()) {
    return 'Укажите имя'
  }
  if ((role === 'user' || role === 'group_senior') && form.value.group_ids.length === 0) {
    return 'Выберите хотя бы одну группу для оператора'
  }
  if (role === 'senior' && form.value.department_id == null) {
    return 'Выберите отдел для старшего'
  }
  return null
}

async function toggleGroupSenior(): Promise<void> {
  if (!editing.value) return
  if (form.value.group_ids.length === 0) {
    message.warning('Сначала назначьте хотя бы одну группу')
    return
  }
  const nextRole = form.value.role === 'group_senior' ? 'user' : 'group_senior'
  promotingGroupSenior.value = true
  try {
    const updated = await updateUser(editing.value.id, {
      full_name: form.value.full_name.trim(),
      role: nextRole,
    })
    form.value.role = updated.role
    editing.value = { ...editing.value, ...updated }
    message.success(
      nextRole === 'group_senior'
        ? 'Повышен до старшего группы (можно передавать карточки)'
        : 'Понижен до оператора',
    )
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось изменить роль')
  } finally {
    promotingGroupSenior.value = false
  }
}

async function onSave(): Promise<void> {
  const role = isSenior.value ? 'user' : form.value.role === 'group_senior' ? 'group_senior' : form.value.role
  const validationError = validateForm(role)
  if (validationError) {
    message.warning(validationError)
    return
  }

  try {
    if (editing.value) {
      const payload: Parameters<typeof updateUser>[1] = {
        full_name: form.value.full_name.trim(),
      }
      // Роль group_senior меняется только кнопкой повышения/понижения.
      if (!isSenior.value && form.value.role !== 'group_senior') {
        payload.role = form.value.role
      }
      if (form.value.role === 'user' || form.value.role === 'group_senior') {
        payload.group_ids = form.value.group_ids
      } else if (form.value.role === 'senior') {
        payload.department_id = form.value.department_id
        payload.group_ids = []
        if (form.value.set_as_department_head) {
          payload.set_as_department_head = true
        }
      } else {
        payload.group_ids = []
      }
      await updateUser(editing.value.id, payload)
      message.success('Пользователь обновлён')
    } else {
      const createRole = isSenior.value ? 'user' : form.value.role
      if (createRole === 'group_senior') {
        message.warning('Старшего группы создайте как оператора, затем повысьте кнопкой')
        return
      }
      await createUser({
        username: form.value.username.trim(),
        full_name: form.value.full_name.trim(),
        password: form.value.password,
        role: createRole,
        group_ids: createRole === 'user' ? form.value.group_ids : [],
        department_id: createRole === 'senior' ? form.value.department_id : null,
        set_as_department_head: createRole === 'senior' && form.value.set_as_department_head,
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
    message.success('Пользователь отключён, карточки распределены по группе')
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
        <NFormItem v-if="showRoleSelect" label="Роль">
          <NSelect v-model:value="form.role" :options="roleOptions" />
        </NFormItem>
        <NFormItem v-else-if="editing && form.role === 'group_senior'" label="Роль">
          <span>Старший группы</span>
        </NFormItem>
        <NFormItem v-if="canToggleGroupSenior" label="Права старшего группы">
          <NSpace vertical :size="6">
            <NButton
              secondary
              :type="form.role === 'group_senior' ? 'default' : 'primary'"
              :loading="promotingGroupSenior"
              @click="toggleGroupSenior"
            >
              {{
                form.role === 'group_senior'
                  ? 'Понизить до оператора'
                  : 'Повысить до старшего группы'
              }}
            </NButton>
            <span class="admin-page__hint">
              Группы и остальное не меняются — добавляется только право передавать карточки в своих
              группах.
            </span>
          </NSpace>
        </NFormItem>
        <NFormItem v-if="showGroupField" label="Группы">
          <NSelect
            v-model:value="form.group_ids"
            :options="groupOptions"
            multiple
            placeholder="Выбрать одну или несколько"
          />
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

.admin-page__hint {
  font-size: 0.75rem;
  line-height: 1.35;
  color: var(--app-text-muted, #888);
}
</style>
