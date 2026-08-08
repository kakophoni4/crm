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
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { listDepartments, listUsers, type AdminUser, type Department } from '@/features/admin/api'
import {
  acknowledgeTask,
  completeTask,
  confirmTask,
  createTask,
  deleteTask,
  getTaskBoard,
  listMyTasks,
  moveTask,
  reopenTask,
  updateTask,
  type DepartmentTask,
  type TaskBoard,
  type TaskStatus,
  type TaskType,
} from '@/features/tasks/api'
import { TASK_TYPE_COLORS } from '@/features/tasks/types'
import { AppError } from '@/shared/api/http'
import { peekCached, setCached } from '@/shared/lib/stale-cache'
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

const mineLoading = ref(false)
const boardLoading = ref(false)
const activeTab = ref(isManager.value ? 'board' : 'mine')
const myTasks = ref<DepartmentTask[]>([])
const board = ref<TaskBoard | null>(null)
const deptUsers = ref<AdminUser[]>([])
const departments = ref<Department[]>([])
const selectedDeptId = ref<number | null>(null)

const draggingTask = ref<DepartmentTask | null>(null)
const dragOverStatus = ref<string | null>(null)

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
    .filter((u) => u.status === 'active')
    .map((u) => ({ label: u.full_name, value: u.id })),
)

const reassignOpen = ref(false)
const reassignLoading = ref(false)
const reassignTask = ref<DepartmentTask | null>(null)
const reassignAssigneeId = ref<number | null>(null)

const boardDepartmentOptions = computed(() =>
  departments.value.map((d) => ({ label: d.name, value: d.id })),
)

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

const MINE_CACHE_KEY = 'tasks:mine'
const boardCacheKey = computed(() => `tasks:board:${selectedDeptId.value ?? 'all'}`)

async function loadMine(): Promise<void> {
  // Спиннер показываем только если совсем нет данных — иначе обновляем в фоне.
  if (!myTasks.value.length) mineLoading.value = true
  try {
    const data = await listMyTasks()
    myTasks.value = data.items
    setCached(MINE_CACHE_KEY, data.items)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить задачи')
  } finally {
    mineLoading.value = false
  }
}

async function loadBoard(): Promise<void> {
  if (!isManager.value) return
  if (!board.value) boardLoading.value = true
  try {
    board.value = await getTaskBoard(
      isAdmin.value && selectedDeptId.value != null ? selectedDeptId.value : undefined,
    )
    setCached(boardCacheKey.value, board.value)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить доску')
  } finally {
    boardLoading.value = false
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
      const deptId = formDepartmentId.value ?? selectedDeptId.value ?? reassignTask.value?.department_id
      if (deptId != null) params.department_id = deptId
      // Admin without dept filter: load all active users for reassign/create.
    } else if (auth.user?.department_id != null) {
      params.department_id = auth.user.department_id
    } else if (reassignTask.value?.department_id != null) {
      params.department_id = reassignTask.value.department_id
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
  if (activeTab.value === 'mine') await loadMine()
  else await loadBoard()
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

async function onAcknowledge(task: DepartmentTask): Promise<void> {
  try {
    await acknowledgeTask(task.id)
    message.success('Задача принята в работу')
    await refresh()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка')
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

function openReassign(task: DepartmentTask): void {
  reassignTask.value = task
  reassignAssigneeId.value = task.assignee_id
  reassignOpen.value = true
  void loadUsers()
}

async function submitReassign(): Promise<void> {
  if (!reassignTask.value || reassignAssigneeId.value == null) {
    message.warning('Выберите исполнителя')
    return
  }
  if (reassignAssigneeId.value === reassignTask.value.assignee_id) {
    reassignOpen.value = false
    return
  }
  reassignLoading.value = true
  try {
    await updateTask(reassignTask.value.id, { assignee_id: reassignAssigneeId.value })
    message.success('Исполнитель изменён')
    reassignOpen.value = false
    await refresh()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось переназначить')
  } finally {
    reassignLoading.value = false
  }
}

function onDragStart(task: DepartmentTask, event: DragEvent): void {
  draggingTask.value = task
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(task.id))
  }
}

function onDragEnd(): void {
  draggingTask.value = null
  dragOverStatus.value = null
}

function onColumnDragOver(status: string, event: DragEvent): void {
  if (!draggingTask.value) return
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
  dragOverStatus.value = status
}

function computeDropIndex(container: HTMLElement, task: DepartmentTask, clientY: number): number {
  const cards = [...container.querySelectorAll<HTMLElement>('[data-task-card]')].filter(
    (el) => el.dataset.taskId !== String(task.id),
  )
  for (let i = 0; i < cards.length; i += 1) {
    const rect = cards[i].getBoundingClientRect()
    if (clientY < rect.top + rect.height / 2) return i
  }
  return cards.length
}

async function onColumnDrop(status: TaskStatus, event: DragEvent): Promise<void> {
  event.preventDefault()
  const task = draggingTask.value
  const container = event.currentTarget as HTMLElement
  onDragEnd()
  if (!task || !board.value) return
  const index = computeDropIndex(container, task, event.clientY)
  await applyMove(task, status, index)
}

async function applyMove(
  task: DepartmentTask,
  status: TaskStatus,
  index: number,
): Promise<void> {
  if (!board.value) return
  const cols = board.value.columns
  const source = cols.find((c) => c.status === task.status)
  const target = cols.find((c) => c.status === status)
  if (!source || !target) return
  if (task.status === status && source.items.indexOf(task) === index) return

  const snapshot = board.value.columns.map((c) => ({ ...c, items: [...c.items] }))
  const moved: DepartmentTask = { ...task, status }
  source.items = source.items.filter((t) => t.id !== task.id)
  const targetItems = target.items.filter((t) => t.id !== task.id)
  targetItems.splice(Math.min(index, targetItems.length), 0, moved)
  target.items = targetItems

  try {
    suppressNextWsRefresh()
    await moveTask(task.id, status, index)
  } catch (err) {
    board.value.columns = snapshot
    message.error(err instanceof AppError ? err.message : 'Не удалось переместить задачу')
    await loadBoard()
  }
}

let unsubTasks: (() => void) | null = null
let wsRefreshTimer: ReturnType<typeof setTimeout> | null = null
let suppressWsUntil = 0

function suppressNextWsRefresh(): void {
  // Skip the WS-triggered reload caused by our own optimistic action.
  suppressWsUntil = Date.now() + 2500
}

function scheduleWsRefresh(): void {
  if (wsRefreshTimer) return
  wsRefreshTimer = setTimeout(() => {
    wsRefreshTimer = null
    if (Date.now() < suppressWsUntil) return
    void refresh()
  }, 800)
}

watch(activeTab, (tab) => {
  if (tab === 'mine') void loadMine()
  else void loadBoard()
})

onMounted(async () => {
  const cachedMine = peekCached<DepartmentTask[]>(MINE_CACHE_KEY)
  if (cachedMine) myTasks.value = cachedMine
  const cachedBoard = peekCached<TaskBoard>(boardCacheKey.value)
  if (cachedBoard) board.value = cachedBoard

  await Promise.all([loadDepartments(), loadUsers(), refresh()])
  await connectTasksRealtime()
  unsubTasks = onTasksEvent((topic, payload) => {
    if (topic === 'task.created' || topic === 'task.due_soon') {
      message.info(showTaskNotification(topic, payload))
    }
    scheduleWsRefresh()
  })
})

onUnmounted(() => {
  unsubTasks?.()
  if (wsRefreshTimer) clearTimeout(wsRefreshTimer)
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
              v-model:value="selectedDeptId"
              :options="boardDepartmentOptions"
              placeholder="Все отделы"
              clearable
              style="max-width: 280px"
              @update:value="onBoardDepartmentChange"
            />
          </div>
          <p class="kanban-hint">Перетаскивайте карточки между колонками, чтобы менять статус.</p>
          <NSpin :show="boardLoading && !board">
            <div v-if="board" class="kanban">
              <div
                v-for="col in board.columns"
                :key="col.status"
                class="kanban-col"
                :class="{ 'kanban-col--over': dragOverStatus === col.status }"
              >
                <h3 class="kanban-col-title">
                  <span class="kanban-col-dot" :class="`kanban-col-dot--${col.status}`" />
                  {{ col.label }}
                  <span class="kanban-col-count">{{ col.items.length }}</span>
                </h3>
                <div
                  class="kanban-cards"
                  @dragover="onColumnDragOver(col.status, $event)"
                  @drop="onColumnDrop(col.status as TaskStatus, $event)"
                >
                  <div
                    v-for="task in col.items"
                    :key="task.id"
                    class="task-card task-card--draggable"
                    :class="{ 'task-card--dragging': draggingTask?.id === task.id }"
                    data-task-card
                    :data-task-id="task.id"
                    draggable="true"
                    @dragstart="onDragStart(task, $event)"
                    @dragend="onDragEnd"
                  >
                    <div class="task-card-head">
                      <NTag
                        :color="{ color: typeColor(task.task_type), textColor: '#fff' }"
                        size="small"
                      >
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
                        v-if="task.status !== 'closed'"
                        size="tiny"
                        secondary
                        @click.stop="openReassign(task)"
                      >
                        Переназначить
                      </NButton>
                      <NButton
                        v-if="task.status === 'done_pending'"
                        size="tiny"
                        type="primary"
                        @click.stop="onConfirm(task)"
                      >
                        <template #icon><Check :size="12" /></template>
                        Подтвердить
                      </NButton>
                      <NButton
                        v-if="task.status === 'done_pending'"
                        size="tiny"
                        @click.stop="onReopen(task)"
                      >
                        <template #icon><RotateCcw :size="12" /></template>
                        Вернуть
                      </NButton>
                      <NButton
                        v-if="task.status !== 'closed'"
                        size="tiny"
                        quaternary
                        type="error"
                        @click.stop="onDelete(task)"
                      >
                        <template #icon><Trash2 :size="12" /></template>
                      </NButton>
                    </NSpace>
                  </div>
                  <p v-if="!col.items.length" class="kanban-empty">Перетащите задачу сюда</p>
                </div>
              </div>
            </div>
          </NSpin>
        </NTabPane>

        <NTabPane name="mine" tab="Мои задачи">
          <NSpin :show="mineLoading && myTasks.length === 0">
            <div v-if="myTasks.length" class="task-list">
              <div v-for="task in myTasks" :key="task.id" class="task-card">
                <div class="task-card-head">
                  <NTag :color="{ color: typeColor(task.task_type), textColor: '#fff' }" size="small">
                    {{ task.task_type_label }}
                  </NTag>
                  <NTag v-if="task.status === 'new'" type="warning" size="small">Новая</NTag>
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
                  v-if="task.status === 'new'"
                  type="primary"
                  size="small"
                  style="margin-right: 8px"
                  @click="onAcknowledge(task)"
                >
                  Принять
                </NButton>
                <NButton
                  v-if="task.status === 'open' || task.status === 'new'"
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

    <NModal
      v-model:show="reassignOpen"
      preset="card"
      title="Переназначить задачу"
      style="width: 420px; max-width: 94vw"
    >
      <p v-if="reassignTask" class="task-card-desc" style="margin-bottom: 12px">
        {{ reassignTask.title }}
      </p>
      <NForm label-placement="top">
        <NFormItem label="Исполнитель" required>
          <NSelect
            v-model:value="reassignAssigneeId"
            :options="assigneeOptions"
            filterable
            placeholder="Выберите исполнителя"
          />
        </NFormItem>
      </NForm>
      <template #footer>
        <NButton type="primary" :loading="reassignLoading" @click="submitReassign">
          Сохранить
        </NButton>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.tasks-page {
  width: 100%;
  padding-bottom: 16px;
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

.kanban-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.kanban {
  display: grid;
  grid-template-columns: repeat(4, minmax(220px, 1fr));
  gap: 16px;
  align-items: start;
  overflow-x: auto;
}

@media (max-width: 900px) {
  .kanban {
    grid-template-columns: 1fr;
  }
}

.kanban-col {
  background: var(--app-surface-elevated);
  border: 1px solid var(--app-border);
  border-radius: var(--app-control-radius);
  padding: 12px;
  min-height: 240px;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.kanban-col--over {
  border-color: var(--app-accent);
  background: var(--app-accent-soft);
}

.kanban-col-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 12px;
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--app-text-muted);
}

.kanban-col-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--app-text-muted);
}

.kanban-col-dot--open {
  background: var(--app-accent);
}

.kanban-col-dot--done_pending {
  background: var(--app-warning);
}

.kanban-col-dot--closed {
  background: var(--app-success);
}

.kanban-col-count {
  margin-left: auto;
  font-size: 12px;
  color: var(--app-text-muted);
}

.kanban-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 120px;
}

.kanban-empty,
.empty-hint {
  color: var(--app-text-muted);
  font-size: 13px;
  text-align: center;
  padding: 24px 8px;
  border: 1px dashed var(--app-border);
  border-radius: var(--app-control-radius);
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 640px;
}

.task-card {
  border: 1px solid var(--app-border);
  border-radius: var(--app-control-radius);
  padding: 12px;
  background: var(--app-surface);
}

.task-card--draggable {
  cursor: grab;
}

.task-card--draggable:active {
  cursor: grabbing;
}

.task-card--dragging {
  opacity: 0.45;
}

.task-card:hover {
  border-color: var(--app-accent);
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
  color: var(--app-text-muted);
  white-space: pre-wrap;
}

.task-card-meta {
  margin: 0 0 4px;
  font-size: 12px;
  color: var(--app-text-muted);
}

.task-card-actions {
  margin-top: 10px;
}
</style>
