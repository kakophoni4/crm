<script setup lang="ts">
import {
  NButton,
  NDatePicker,
  NForm,
  NFormItem,
  NInput,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  useMessage,
} from 'naive-ui'
import { Check, Plus, RotateCcw, Trash2 } from 'lucide-vue-next'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { listDepartments, listUsers, type AdminUser, type Department } from '@/features/admin/api'
import {
  completeTask,
  confirmTask,
  createTask,
  deleteTask,
  getTaskBoard,
  listMyTasks,
  reopenTask,
  type DepartmentTask,
  type TaskBoard,
  type TaskType,
} from '@/features/tasks/api'
import { TASK_TYPE_COLORS } from '@/features/tasks/types'
import { AppError } from '@/shared/api/http'
import {
  connectTasksRealtime,
  onTasksEvent,
  showTaskNotification,
} from '@/shared/realtime/tasks-ws'
import { useAuthStore } from '@/shared/store/auth'
import AppCard from '@/shared/ui/AppCard.vue'

const message = useMessage()
const auth = useAuthStore()

const isManager = computed(
  () =>
    auth.user?.role === 'senior' ||
    auth.user?.role === 'admin' ||
    auth.user?.permissions.includes('tasks.manage'),
)

const isAdmin = computed(() => auth.user?.role === 'admin')

const loading = ref(false)
const activeTab = ref(isManager.value ? 'board' : 'mine')
const myTasks = ref<DepartmentTask[]>([])
const board = ref<TaskBoard | null>(null)
const deptUsers = ref<AdminUser[]>([])
const departments = ref<Department[]>([])
const selectedDeptId = ref<number | null>(null)

const createOpen = ref(false)
const createLoading = ref(false)
const formTitle = ref('')
const formDescription = ref('')
const formType = ref<TaskType>('normal')
const formAssigneeId = ref<number | null>(null)
const formDepartmentId = ref<number | null>(null)
const formDueAt = ref<number | null>(null)

const typeOptions = computed(() =>
  (board.value?.task_types ?? [
    { value: 'urgent', label: 'Срочная' },
    { value: 'high', label: 'Высокий приоритет' },
    { value: 'normal', label: 'Обычная' },
    { value: 'low', label: 'Низкий приоритет' },
  ]).map((t) => ({ label: t.label, value: t.value })),
)

const assigneeOptions = computed(() =>
  deptUsers.value
    .filter((u) => u.role === 'user' && u.status === 'active')
    .map((u) => ({ label: u.full_name, value: u.id })),
)

const departmentOptions = computed(() => [
  { label: 'Все отделы', value: null as number | null },
  ...departments.value.map((d) => ({ label: d.name, value: d.id })),
])

const departmentMap = computed(() =>
  Object.fromEntries(departments.value.map((d) => [d.id, d.name])),
)

const showAllDepartments = computed(() => isAdmin.value && selectedDeptId.value == null)

function formatDue(iso: string | null): string {
  if (!iso) return 'Без срока'
  return new Date(iso).toLocaleString('ru-RU')
}

function typeColor(type: string): string {
  return TASK_TYPE_COLORS[type as TaskType] ?? '#909399'
}

async function loadMine(): Promise<void> {
  loading.value = true
  try {
    const data = await listMyTasks()
    myTasks.value = data.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить задачи')
  } finally {
    loading.value = false
  }
}

async function loadBoard(): Promise<void> {
  if (!isManager.value) return
  loading.value = true
  try {
    board.value = await getTaskBoard(
      isAdmin.value && selectedDeptId.value != null ? selectedDeptId.value : undefined,
    )
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить доску')
  } finally {
    loading.value = false
  }
}

async function loadDepartments(): Promise<void> {
  if (!isAdmin.value) return
  try {
    departments.value = await listDepartments()
  } catch {
    departments.value = []
  }
}

async function loadUsers(): Promise<void> {
  if (!isManager.value) return
  try {
    const params: { department_id?: number } = {}
    if (isAdmin.value) {
      const deptId = formDepartmentId.value ?? selectedDeptId.value
      if (deptId != null) params.department_id = deptId
    } else if (auth.user?.department_id != null) {
      params.department_id = auth.user.department_id
    } else {
      return
    }
    deptUsers.value = await listUsers(params)
  } catch {
    deptUsers.value = []
  }
}

async function onBoardDepartmentChange(deptId: number | null): Promise<void> {
  selectedDeptId.value = deptId
  await loadBoard()
}

async function onCreateDepartmentChange(): Promise<void> {
  formAssigneeId.value = null
  await loadUsers()
}

async function refresh(): Promise<void> {
  await Promise.all([loadMine(), loadBoard()])
}

function openCreate(): void {
  formTitle.value = ''
  formDescription.value = ''
  formType.value = 'normal'
  formAssigneeId.value = null
  formDepartmentId.value = isAdmin.value ? selectedDeptId.value : auth.user?.department_id ?? null
  formDueAt.value = null
  createOpen.value = true
  void loadUsers()
}

async function submitCreate(): Promise<void> {
  if (!formTitle.value.trim() || formAssigneeId.value == null) {
    message.warning('Укажите название и исполнителя')
    return
  }
  if (isAdmin.value && formDepartmentId.value == null) {
    message.warning('Выберите отдел')
    return
  }
  createLoading.value = true
  try {
    await createTask({
      title: formTitle.value.trim(),
      description: formDescription.value.trim() || null,
      task_type: formType.value,
      assignee_id: formAssigneeId.value,
      department_id: isAdmin.value ? formDepartmentId.value ?? undefined : undefined,
      due_at: formDueAt.value ? new Date(formDueAt.value).toISOString() : null,
    })
    message.success('Задача создана')
    createOpen.value = false
    await refresh()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось создать задачу')
  } finally {
    createLoading.value = false
  }
}

async function onComplete(task: DepartmentTask): Promise<void> {
  try {
    await completeTask(task.id)
    message.success('Отмечено как выполненное — ждёт подтверждения старшего')
    await refresh()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка')
  }
}

async function onConfirm(task: DepartmentTask): Promise<void> {
  try {
    await confirmTask(task.id)
    message.success('Задача подтверждена и закрыта')
    await refresh()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка')
  }
}

async function onReopen(task: DepartmentTask): Promise<void> {
  try {
    await reopenTask(task.id)
    message.info('Задача возвращена исполнителю')
    await refresh()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка')
  }
}

async function onDelete(task: DepartmentTask): Promise<void> {
  try {
    await deleteTask(task.id)
    message.success('Задача снята')
    await refresh()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка')
  }
}

let unsubTasks: (() => void) | null = null

onMounted(async () => {
  await loadDepartments()
  await loadUsers()
  await refresh()
  await connectTasksRealtime()
  unsubTasks = onTasksEvent((topic, payload) => {
    message.info(showTaskNotification(topic, payload))
    void refresh()
  })
})

onUnmounted(() => {
  unsubTasks?.()
})
</script>

<template>
  <div class="tasks-page">
    <AppCard>
      <div class="tasks-header">
        <h2 class="tasks-title">Задачи</h2>
        <NButton v-if="isManager" type="primary" @click="openCreate">
          <template #icon><Plus :size="16" /></template>
          Новая задача
        </NButton>
      </div>

      <NTabs v-model:value="activeTab" type="line" style="margin-top: 16px">
        <NTabPane v-if="isManager" name="board" tab="Доска отдела">
          <div v-if="isAdmin" class="dept-filter">
            <NSelect
              :value="selectedDeptId"
              :options="departmentOptions"
              placeholder="Отдел"
              style="max-width: 280px"
              @update:value="onBoardDepartmentChange"
            />
          </div>
          <NSpin :show="loading">
            <div v-if="board" class="kanban">
              <div v-for="col in board.columns" :key="col.status" class="kanban-col">
                <h3 class="kanban-col-title">{{ col.label }} ({{ col.items.length }})</h3>
                <div v-for="task in col.items" :key="task.id" class="task-card">
                  <div class="task-card-head">
                    <NTag :color="{ color: typeColor(task.task_type), textColor: '#fff' }" size="small">
                      {{ task.task_type_label }}
                    </NTag>
                    <NTag v-if="task.is_overdue" type="error" size="small">Просрочена</NTag>
                    <NTag v-else-if="task.due_soon" type="warning" size="small">Скоро срок</NTag>
                  </div>
                  <p class="task-card-title">{{ task.title }}</p>
                  <p v-if="task.description" class="task-card-desc">{{ task.description }}</p>
                  <p v-if="showAllDepartments" class="task-card-meta">
                    Отдел: {{ departmentMap[task.department_id] ?? task.department_id }}
                  </p>
                  <p class="task-card-meta">Исполнитель: {{ task.assignee?.full_name ?? '—' }}</p>
                  <p class="task-card-meta">Срок: {{ formatDue(task.due_at) }}</p>
                  <NSpace size="small" class="task-card-actions">
                    <NButton
                      v-if="task.status === 'done_pending'"
                      size="tiny"
                      type="primary"
                      @click="onConfirm(task)"
                    >
                      <template #icon><Check :size="12" /></template>
                      Подтвердить
                    </NButton>
                    <NButton
                      v-if="task.status === 'done_pending'"
                      size="tiny"
                      @click="onReopen(task)"
                    >
                      <template #icon><RotateCcw :size="12" /></template>
                      Вернуть
                    </NButton>
                    <NButton size="tiny" quaternary type="error" @click="onDelete(task)">
                      <template #icon><Trash2 :size="12" /></template>
                    </NButton>
                  </NSpace>
                </div>
                <p v-if="!col.items.length" class="kanban-empty">Нет задач</p>
              </div>
            </div>
          </NSpin>
        </NTabPane>

        <NTabPane name="mine" tab="Мои задачи">
          <NSpin :show="loading">
            <div v-if="myTasks.length" class="task-list">
              <div v-for="task in myTasks" :key="task.id" class="task-card">
                <div class="task-card-head">
                  <NTag :color="{ color: typeColor(task.task_type), textColor: '#fff' }" size="small">
                    {{ task.task_type_label }}
                  </NTag>
                  <NTag v-if="task.status === 'done_pending'" type="info" size="small">
                    На проверке
                  </NTag>
                  <NTag v-if="task.is_overdue" type="error" size="small">Просрочена</NTag>
                  <NTag v-else-if="task.due_soon" type="warning" size="small">Скоро срок</NTag>
                </div>
                <p class="task-card-title">{{ task.title }}</p>
                <p v-if="task.description" class="task-card-desc">{{ task.description }}</p>
                <p class="task-card-meta">Срок: {{ formatDue(task.due_at) }}</p>
                <p class="task-card-meta">Поставил: {{ task.creator?.full_name ?? 'Старший оператор' }}</p>
                <NButton
                  v-if="task.status === 'open'"
                  type="primary"
                  size="small"
                  @click="onComplete(task)"
                >
                  <template #icon><Check :size="14" /></template>
                  Выполнено
                </NButton>
              </div>
            </div>
            <p v-else class="empty-hint">Нет активных задач</p>
          </NSpin>
        </NTabPane>
      </NTabs>
    </AppCard>

    <NModal v-model:show="createOpen" preset="card" title="Новая задача" style="width: 480px">
      <NForm label-placement="top">
        <NFormItem label="Название" required>
          <NInput v-model:value="formTitle" maxlength="512" />
        </NFormItem>
        <NFormItem label="Описание">
          <NInput v-model:value="formDescription" type="textarea" :rows="3" />
        </NFormItem>
        <NFormItem label="Тип" required>
          <NSelect v-model:value="formType" :options="typeOptions" />
        </NFormItem>
        <NFormItem v-if="isAdmin" label="Отдел" required>
          <NSelect
            v-model:value="formDepartmentId"
            :options="departments.map((d) => ({ label: d.name, value: d.id }))"
            filterable
            @update:value="onCreateDepartmentChange"
          />
        </NFormItem>
        <NFormItem label="Исполнитель" required>
          <NSelect v-model:value="formAssigneeId" :options="assigneeOptions" filterable />
        </NFormItem>
        <NFormItem label="Срок выполнения">
          <NDatePicker
            v-model:value="formDueAt"
            type="datetime"
            clearable
            style="width: 100%"
          />
        </NFormItem>
        <NButton type="primary" block :loading="createLoading" @click="submitCreate">
          Создать
        </NButton>
      </NForm>
    </NModal>
  </div>
</template>

<style scoped>
.tasks-page {
  padding: 16px;
  max-width: 1280px;
  margin: 0 auto;
}

.tasks-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.tasks-title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
}

.dept-filter {
  margin-bottom: 16px;
}

.kanban {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
  align-items: start;
}

.kanban-col {
  background: var(--n-action-color);
  border-radius: 10px;
  padding: 12px;
  min-height: 200px;
}

.kanban-col-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
}

.kanban-empty,
.empty-hint {
  color: var(--n-text-color-3);
  font-size: 13px;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 640px;
}

.task-card {
  border: 1px solid var(--n-border-color);
  border-radius: 10px;
  padding: 12px;
  background: var(--n-color);
  margin-bottom: 10px;
}

.task-card-head {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.task-card-title {
  margin: 0 0 6px;
  font-weight: 600;
  font-size: 15px;
}

.task-card-desc {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--n-text-color-2);
  white-space: pre-wrap;
}

.task-card-meta {
  margin: 0 0 4px;
  font-size: 12px;
  color: var(--n-text-color-3);
}

.task-card-actions {
  margin-top: 10px;
}
</style>
