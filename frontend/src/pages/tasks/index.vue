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
  NSwitch,
  NTabPane,
  NTabs,
  NTag,
  NUpload,
  useDialog,
  useMessage,
} from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { Check, Plus, RotateCcw, Trash2 } from 'lucide-vue-next'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { listDepartments, type Department } from '@/features/admin/api'
import {
  acknowledgeTask,
  completeTask,
  confirmTask,
  createTask,
  deleteTask,
  formatTaskAssigneeLabel,
  getTaskBoard,
  listMyTasks,
  listTaskAssignees,
  moveTask,
  reopenTask,
  handoffTask,
  updateTask,
  type DepartmentTask,
  type TaskAssigneeOption,
  type TaskBoard,
  type TaskListQuery,
  type TaskStatus,
  type TaskType,
  type TaskWorkloadSummary,
} from '@/features/tasks/api'
import { TASK_TYPE_COLORS } from '@/features/tasks/types'
import {
  sortTasks,
  taskDeadline,
  taskIsOverdue,
  type TaskSortMode,
} from '@/features/tasks/due'
import { uploadFile } from '@/features/chats/api'
import { AppError } from '@/shared/api/http'
import { peekCached, setCached } from '@/shared/lib/stale-cache'
import {
  connectTasksRealtime,
  onTasksEvent,
  showTaskNotification,
} from '@/shared/realtime/tasks-ws'
import { useAuthStore } from '@/shared/store/auth'
import AppCard from '@/shared/ui/AppCard.vue'
import TaskDetailModal from '@/widgets/tasks/TaskDetailModal.vue'

const message = useMessage()
const dialog = useDialog()
const auth = useAuthStore()

const isManager = computed(() => auth.canManageTasks)
const canCreateTasks = computed(() => auth.canCreateTasks)

const isAdmin = computed(() => auth.user?.role === 'admin')

const mineLoading = ref(false)
const boardLoading = ref(false)
const activeTab = ref(isManager.value ? 'board' : 'mine')
const myTasks = ref<DepartmentTask[]>([])
const board = ref<TaskBoard | null>(null)
const assigneeUsers = ref<TaskAssigneeOption[]>([])
const departments = ref<Department[]>([])
const selectedDeptId = ref<number | null>(null)

type TaskViewFilter = TaskStatus | 'overdue' | 'due_soon'
const REAL_TASK_STATUSES = new Set<TaskStatus>(['new', 'open', 'done_pending', 'closed', 'deleted'])

const filterQuery = ref('')
const filterQueryDebounced = ref('')
const filterAssigneeId = ref<number | null>(null)
const filterCreatedBy = ref<number | null>(null)
const filterStatus = ref<TaskViewFilter | null>(null)
const sortMode = ref<TaskSortMode>('due')
const includeClosedMine = ref(true)
const includeClosedBoard = ref(true)
type MineBucket = 'active' | 'review' | 'done'
const mineBucket = ref<MineBucket>('active')
const mineSummary = ref<TaskWorkloadSummary | null>(null)
const nowMs = ref(Date.now())
let queryDebounceTimer: ReturnType<typeof setTimeout> | null = null
let dueTickTimer: ReturnType<typeof setInterval> | null = null

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
const formFiles = ref<File[]>([])
const formUploadKey = ref(0)

const typeOptions = computed(() =>
  (board.value?.task_types ?? [
    { value: 'urgent', label: 'Срочная' },
    { value: 'high', label: 'Высокий приоритет' },
    { value: 'normal', label: 'Обычная' },
    { value: 'low', label: 'Низкий приоритет' },
  ]).map((t) => ({ label: t.label, value: t.value })),
)

const assigneeOptions = computed(() =>
  assigneeUsers.value.map((u) => ({
    label: formatTaskAssigneeLabel(u, auth.user?.id),
    value: u.id,
  })),
)

const statusFilterOptions = computed(() => {
  const options: { label: string; value: TaskViewFilter }[] = [
    { label: 'Просроченные', value: 'overdue' },
    { label: 'Скоро срок', value: 'due_soon' },
    { label: 'Новые', value: 'new' },
    { label: 'В работе', value: 'open' },
    { label: 'На проверке', value: 'done_pending' },
    { label: 'Готово', value: 'closed' },
  ]
  if (isAdmin.value) {
    options.push({ label: 'Удалённые', value: 'deleted' })
  }
  return options
})

const sortOptions: { label: string; value: TaskSortMode }[] = [
  { label: 'По сроку', value: 'due' },
  { label: 'По приоритету', value: 'priority' },
  { label: 'По дате создания', value: 'created' },
]

const hasTaskFilters = computed(
  () =>
    filterAssigneeId.value != null ||
    filterCreatedBy.value != null ||
    Boolean(filterQueryDebounced.value) ||
    filterStatus.value != null,
)

const includeClosed = computed({
  get: () => (activeTab.value === 'board' ? includeClosedBoard.value : includeClosedMine.value),
  set: (value: boolean) => {
    if (activeTab.value === 'board') includeClosedBoard.value = value
    else includeClosedMine.value = value
  },
})

function currentQuery(): TaskListQuery {
  const status = filterStatus.value
  return {
    assignee_id: filterAssigneeId.value,
    created_by: filterCreatedBy.value,
    q: filterQueryDebounced.value || null,
    status: status && REAL_TASK_STATUSES.has(status as TaskStatus) ? (status as TaskStatus) : null,
    include_closed: includeClosed.value,
  }
}

function formatWorkload(summary: TaskWorkloadSummary | null | undefined): string {
  if (!summary || summary.total <= 0) return ''
  const parts: string[] = []
  if (summary.new) parts.push(`новые ${summary.new}`)
  if (summary.open) parts.push(`в работе ${summary.open}`)
  if (summary.overdue) parts.push(`просрочено ${summary.overdue}`)
  if (summary.pending_review) parts.push(`на проверке ${summary.pending_review}`)
  if (summary.done) parts.push(`готово ${summary.done}`)
  if (summary.deleted) parts.push(`удалено ${summary.deleted}`)
  return `Всего ${summary.total}${parts.length ? `: ${parts.join(' · ')}` : ''}`
}

const currentSummaryText = computed(() =>
  activeTab.value === 'board'
    ? formatWorkload(board.value?.summary)
    : formatWorkload(mineSummary.value),
)

function matchesDueFilter(task: DepartmentTask): boolean {
  if (filterStatus.value === 'overdue') return taskIsOverdue(task, nowMs.value)
  if (filterStatus.value === 'due_soon') {
    return Boolean(task.due_soon) && !taskIsOverdue(task, nowMs.value)
  }
  return true
}

function cardIsOverdue(task: DepartmentTask): boolean {
  return taskIsOverdue(task, nowMs.value)
}

function deadlineFor(task: DepartmentTask) {
  return taskDeadline(task.due_at, nowMs.value)
}

const mineActiveTasks = computed(() =>
  myTasks.value.filter((task) => task.status === 'new' || task.status === 'open'),
)
const mineReviewTasks = computed(() =>
  myTasks.value.filter((task) => task.status === 'done_pending'),
)
const mineDoneTasks = computed(() =>
  myTasks.value.filter((task) => task.status === 'closed' || task.status === 'deleted'),
)
const visibleMineTasks = computed(() => {
  let rows: DepartmentTask[]
  if (filterStatus.value === 'overdue') {
    rows = myTasks.value.filter((task) => taskIsOverdue(task, nowMs.value))
  } else if (filterStatus.value === 'due_soon') {
    rows = myTasks.value.filter((task) => task.due_soon && !taskIsOverdue(task, nowMs.value))
  } else if (mineBucket.value === 'review') {
    rows = mineReviewTasks.value
  } else if (mineBucket.value === 'done') {
    rows = mineDoneTasks.value
  } else {
    rows = mineActiveTasks.value
  }
  return sortTasks(rows, sortMode.value, nowMs.value)
})
const displayedBoard = computed(() => {
  if (!board.value) return null
  return {
    ...board.value,
    columns: board.value.columns.map((col) => ({
      ...col,
      items: sortTasks(col.items.filter(matchesDueFilter), sortMode.value, nowMs.value),
    })),
  }
})
const mineEmptyHint = computed(() => {
  if (filterStatus.value === 'overdue') return 'Нет просроченных задач'
  if (filterStatus.value === 'due_soon') return 'Нет задач со скорым сроком'
  if (hasTaskFilters.value) return 'Нет задач по выбранным фильтрам'
  if (mineBucket.value === 'review') return 'Нет задач на проверке'
  if (mineBucket.value === 'done') return 'Нет выполненных задач'
  return 'Нет активных задач'
})

function resetTaskFilters(): void {
  filterQuery.value = ''
  filterQueryDebounced.value = ''
  filterAssigneeId.value = null
  filterCreatedBy.value = null
  filterStatus.value = null
  includeClosedMine.value = true
  includeClosedBoard.value = true
}

const reassignOpen = ref(false)
const reassignLoading = ref(false)
const reassignTask = ref<DepartmentTask | null>(null)
const reassignAssigneeId = ref<number | null>(null)

const detailOpen = ref(false)
const detailTaskId = ref<number | null>(null)

function isAssignedToMe(task: DepartmentTask): boolean {
  const uid = auth.user?.id
  if (uid == null) return false
  if (task.assignee_id === uid) return true
  return (task.collaborators ?? []).some((row) => row.id === uid)
}

function canReassignTask(task: DepartmentTask): boolean {
  if (task.status === 'closed' || task.status === 'deleted') return false
  const uid = auth.user?.id
  if (uid != null && (task.created_by === uid || task.assignee_id === uid)) return true
  return isManager.value
}

function canReviewTask(task: DepartmentTask): boolean {
  if (task.status !== 'done_pending') return false
  if (isManager.value) return true
  return auth.user?.id != null && task.created_by === auth.user.id
}

function openTaskDetail(task: DepartmentTask): void {
  detailTaskId.value = task.id
  detailOpen.value = true
}

function onOpenRelatedTask(id: number): void {
  detailTaskId.value = id
}

const boardDepartmentOptions = computed(() =>
  departments.value.map((d) => ({ label: d.name, value: d.id })),
)

const departmentMap = computed(() =>
  Object.fromEntries(departments.value.map((d) => [d.id, d.name])),
)

const showAllDepartments = computed(() => isAdmin.value && selectedDeptId.value == null)

const kanbanGridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${displayedBoard.value?.columns.length || 3}, minmax(200px, 1fr))`,
}))

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
    const data = await listMyTasks(currentQuery())
    myTasks.value = data.items
    mineSummary.value = data.summary ?? null
    if (!hasTaskFilters.value && !includeClosedMine.value) {
      setCached(MINE_CACHE_KEY, data.items)
    }
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
      currentQuery(),
    )
    if (!hasTaskFilters.value) {
      setCached(boardCacheKey.value, board.value)
    }
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

async function loadAssignees(): Promise<void> {
  try {
    assigneeUsers.value = await listTaskAssignees()
  } catch {
    assigneeUsers.value = []
  }
}

async function onBoardDepartmentChange(deptId: number | null): Promise<void> {
  selectedDeptId.value = deptId
  await loadBoard()
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
  formFiles.value = []
  formUploadKey.value += 1
  createOpen.value = true
  void loadAssignees()
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
    const fileIds: number[] = []
    for (const file of formFiles.value) {
      const uploaded = await uploadFile(file)
      fileIds.push(uploaded.id)
    }
    await createTask({
      title: formTitle.value.trim(),
      description: formDescription.value.trim() || null,
      task_type: formType.value,
      assignee_id: formAssigneeId.value,
      department_id: isAdmin.value ? formDepartmentId.value ?? undefined : undefined,
      due_at: formDueAt.value ? new Date(formDueAt.value).toISOString() : null,
      file_ids: fileIds,
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
  dialog.warning({
    title: 'Отметить выполненной?',
    content: `Задача «${task.title}» уйдёт на проверку постановщику.`,
    positiveText: 'Выполнено',
    negativeText: 'Отмена',
    onPositiveClick: async () => {
      try {
        await completeTask(task.id)
        message.success('Отмечено как выполненное — ждёт подтверждения постановщика')
        await refresh()
      } catch (err) {
        message.error(err instanceof AppError ? err.message : 'Ошибка')
      }
    },
  })
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
    message.success('Задача перенесена в удалённые')
    await refresh()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка')
  }
}

async function onRestore(task: DepartmentTask): Promise<void> {
  try {
    await moveTask(task.id, 'open', 0)
    message.success('Задача возвращена в работу')
    await refresh()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка')
  }
}

function onPurge(task: DepartmentTask): void {
  dialog.warning({
    title: 'Удалить безвозвратно?',
    content: `Задача «${task.title}» будет удалена навсегда. Это нельзя отменить.`,
    positiveText: 'Удалить',
    negativeText: 'Отмена',
    onPositiveClick: async () => {
      try {
        await deleteTask(task.id, { permanent: true })
        message.success('Задача удалена навсегда')
        await refresh()
      } catch (err) {
        message.error(err instanceof AppError ? err.message : 'Ошибка')
      }
    },
  })
}

function openReassign(task: DepartmentTask): void {
  reassignTask.value = task
  reassignAssigneeId.value = task.assignee_id
  reassignOpen.value = true
  void loadAssignees()
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
    if (isManager.value) {
      await updateTask(reassignTask.value.id, { assignee_id: reassignAssigneeId.value })
    } else {
      await handoffTask(reassignTask.value.id, {
        action: 'transfer',
        user_id: reassignAssigneeId.value,
      })
    }
    message.success('Исполнитель изменён')
    reassignOpen.value = false
    await refresh()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось переназначить')
  } finally {
    reassignLoading.value = false
  }
}

function onCreateUploadChange(options: { fileList: UploadFileInfo[] }): void {
  formFiles.value = options.fileList
    .map((item) => item.file)
    .filter((file): file is File => file instanceof File)
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

watch(mineBucket, (bucket) => {
  if (bucket === 'done' && !includeClosedMine.value) {
    includeClosedMine.value = true
  }
})

watch(filterStatus, (status) => {
  if (status === 'done_pending') mineBucket.value = 'review'
  else if (status === 'closed' || status === 'deleted') mineBucket.value = 'done'
  else if (status === 'new' || status === 'open') mineBucket.value = 'active'
})

watch(filterQuery, (value) => {
  if (queryDebounceTimer) clearTimeout(queryDebounceTimer)
  queryDebounceTimer = setTimeout(() => {
    filterQueryDebounced.value = value.trim()
  }, 300)
})

watch([filterAssigneeId, filterCreatedBy], ([assignee, creator]) => {
  if ((assignee != null || creator != null) && isAdmin.value) {
    includeClosedMine.value = true
    includeClosedBoard.value = true
  }
})

watch(
  [
    filterAssigneeId,
    filterCreatedBy,
    filterQueryDebounced,
    filterStatus,
    includeClosedMine,
    includeClosedBoard,
  ],
  () => {
    void refresh()
  },
)

watch(filterStatus, (value) => {
  if (value === 'overdue' || value === 'due_soon') {
    mineBucket.value = 'active'
  }
})

onMounted(async () => {
  const cachedMine = peekCached<DepartmentTask[]>(MINE_CACHE_KEY)
  if (cachedMine) myTasks.value = cachedMine
  const cachedBoard = peekCached<TaskBoard>(boardCacheKey.value)
  if (cachedBoard) board.value = cachedBoard

  dueTickTimer = setInterval(() => {
    nowMs.value = Date.now()
  }, 60_000)

  await Promise.all([loadDepartments(), loadAssignees(), refresh()])
  await connectTasksRealtime()
  unsubTasks = onTasksEvent((topic, payload) => {
    if (
      topic === 'task.created' ||
      topic === 'task.due_soon' ||
      topic === 'task.notify'
    ) {
      message.info(showTaskNotification(topic, payload))
    }
    scheduleWsRefresh()
  })
})

onUnmounted(() => {
  unsubTasks?.()
  if (wsRefreshTimer) clearTimeout(wsRefreshTimer)
  if (queryDebounceTimer) clearTimeout(queryDebounceTimer)
  if (dueTickTimer) clearInterval(dueTickTimer)
})
</script>

<template>
  <div class="tasks-page">
    <AppCard>
      <div class="tasks-header">
        <h2 class="tasks-title">Задачи</h2>
        <NButton v-if="canCreateTasks" type="primary" @click="openCreate">
          <template #icon><Plus :size="16" /></template>
          Новая задача
        </NButton>
      </div>

      <div class="task-filters">
        <NInput
          v-model:value="filterQuery"
          clearable
          placeholder="Поиск по названию или описанию"
          style="min-width: 220px; flex: 1"
        />
        <NSelect
          v-model:value="filterAssigneeId"
          :options="assigneeOptions"
          filterable
          clearable
          placeholder="Исполнитель"
          style="min-width: 200px; flex: 1"
        />
        <NSelect
          v-model:value="filterCreatedBy"
          :options="assigneeOptions"
          filterable
          clearable
          placeholder="Постановщик"
          style="min-width: 200px; flex: 1"
        />
        <NSelect
          v-model:value="filterStatus"
          :options="statusFilterOptions"
          clearable
          placeholder="Статус"
          style="min-width: 170px"
        />
        <NSelect
          v-model:value="sortMode"
          :options="sortOptions"
          placeholder="Сортировка"
          style="min-width: 180px"
        />
        <label v-if="activeTab === 'board'" class="task-filters__closed">
          <NSwitch v-model:value="includeClosed" size="small" />
          Показать готовые
        </label>
        <NButton v-if="hasTaskFilters" quaternary @click="resetTaskFilters">Сбросить</NButton>
      </div>
      <p v-if="currentSummaryText" class="task-filters__summary">{{ currentSummaryText }}</p>

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
          <NSpin :show="boardLoading && !board">
            <div v-if="displayedBoard" class="kanban" :style="kanbanGridStyle">
              <div
                v-for="col in displayedBoard.columns"
                :key="col.status"
                class="kanban-col"
                :class="{
                  'kanban-col--over': dragOverStatus === col.status,
                  'kanban-col--deleted': col.status === 'deleted',
                }"
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
                    :class="{
                      'task-card--dragging': draggingTask?.id === task.id,
                      'task-card--overdue': cardIsOverdue(task),
                      'task-card--due-soon': task.due_soon && !cardIsOverdue(task),
                      [`task-card--${task.status}`]: true,
                    }"
                    data-task-card
                    :data-task-id="task.id"
                    draggable="true"
                    @click="openTaskDetail(task)"
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
                      <NTag v-if="cardIsOverdue(task)" type="error" size="small">Просрочена</NTag>
                      <NTag v-else-if="task.due_soon" type="warning" size="small">Скоро срок</NTag>
                    </div>
                    <p class="task-card-title">{{ task.title }}</p>
                    <p v-if="task.description" class="task-card-desc">{{ task.description }}</p>
                    <p v-if="showAllDepartments" class="task-card-meta">
                      Отдел: {{ departmentMap[task.department_id] ?? task.department_id }}
                    </p>
                    <p class="task-card-meta">Исполнитель: {{ task.assignee?.full_name ?? '—' }}</p>
                    <p class="task-card-meta">Поставил: {{ task.creator?.full_name ?? '—' }}</p>
                    <p class="task-card-meta task-card__due">
                      <span
                        class="task-card__due-date"
                        :class="{ 'task-card__due-date--overdue': cardIsOverdue(task) }"
                      >
                        Срок: {{ formatDue(task.due_at) }}
                      </span>
                      <span
                        v-if="task.due_at && task.status !== 'closed' && task.status !== 'deleted'"
                        class="task-card__countdown"
                        :class="`task-card__countdown--${deadlineFor(task).tone}`"
                      >
                        {{ deadlineFor(task).text }}
                      </span>
                    </p>
                    <NSpace size="small" class="task-card-actions">
                      <NButton
                        v-if="canReassignTask(task)"
                        size="tiny"
                        secondary
                        @click.stop="openReassign(task)"
                      >
                        Переназначить
                      </NButton>
                      <NButton
                        v-if="
                          (task.status === 'open' || task.status === 'new') &&
                          isAssignedToMe(task)
                        "
                        size="tiny"
                        type="primary"
                        @click.stop="onComplete(task)"
                      >
                        <template #icon><Check :size="12" /></template>
                        Выполнено
                      </NButton>
                      <NButton
                        v-if="canReviewTask(task)"
                        size="tiny"
                        type="primary"
                        @click.stop="onConfirm(task)"
                      >
                        <template #icon><Check :size="12" /></template>
                        Подтвердить
                      </NButton>
                      <NButton
                        v-if="canReviewTask(task)"
                        size="tiny"
                        @click.stop="onReopen(task)"
                      >
                        <template #icon><RotateCcw :size="12" /></template>
                        Вернуть
                      </NButton>
                      <NButton
                        v-if="task.status === 'deleted' && isAdmin"
                        size="tiny"
                        secondary
                        @click.stop="onRestore(task)"
                      >
                        <template #icon><RotateCcw :size="12" /></template>
                        Вернуть
                      </NButton>
                      <NButton
                        v-if="task.status === 'deleted' && isAdmin"
                        size="tiny"
                        type="error"
                        @click.stop="onPurge(task)"
                      >
                        <template #icon><Trash2 :size="12" /></template>
                        Навсегда
                      </NButton>
                      <NButton
                        v-if="task.status !== 'deleted' && (task.status !== 'closed' || isAdmin)"
                        size="tiny"
                        quaternary
                        type="error"
                        @click.stop="onDelete(task)"
                      >
                        <template #icon><Trash2 :size="12" /></template>
                      </NButton>
                    </NSpace>
                  </div>
                  <p v-if="!col.items.length" class="kanban-empty">
                    {{
                      col.status === 'deleted'
                        ? 'Удалённые задачи'
                        : hasTaskFilters
                          ? 'Нет задач по фильтру'
                          : 'Перетащите задачу сюда'
                    }}
                  </p>
                </div>
              </div>
            </div>
          </NSpin>
        </NTabPane>

        <NTabPane name="mine" tab="Мои задачи">
          <NTabs
            v-if="filterStatus !== 'overdue' && filterStatus !== 'due_soon'"
            v-model:value="mineBucket"
            type="segment"
            size="small"
            class="mine-buckets"
          >
            <NTabPane name="active" :tab="`Активные · ${mineActiveTasks.length}`" />
            <NTabPane name="review" :tab="`На проверке · ${mineReviewTasks.length}`" />
            <NTabPane name="done" :tab="`Готово · ${mineDoneTasks.length}`" />
          </NTabs>
          <NSpin :show="mineLoading && myTasks.length === 0">
            <div v-if="visibleMineTasks.length" class="task-list">
              <div
                v-for="task in visibleMineTasks"
                :key="task.id"
                class="task-card task-card--clickable"
                :class="{
                  [`task-card--${task.status}`]: true,
                  'task-card--overdue': cardIsOverdue(task),
                  'task-card--due-soon': task.due_soon && !cardIsOverdue(task),
                }"
                @click="openTaskDetail(task)"
              >
                <div class="task-card-head">
                  <NTag :color="{ color: typeColor(task.task_type), textColor: '#fff' }" size="small">
                    {{ task.task_type_label }}
                  </NTag>
                  <NTag v-if="task.status === 'new'" type="warning" size="small">Новая</NTag>
                  <NTag v-else-if="task.status === 'open'" size="small">В работе</NTag>
                  <NTag v-else-if="task.status === 'done_pending'" type="info" size="small">
                    На проверке
                  </NTag>
                  <NTag v-else-if="task.status === 'closed'" type="success" size="small">
                    Готово
                  </NTag>
                  <NTag v-if="cardIsOverdue(task)" type="error" size="small">Просрочена</NTag>
                  <NTag v-else-if="task.due_soon" type="warning" size="small">Скоро срок</NTag>
                  <NTag
                    v-if="task.created_by === auth.user?.id && task.assignee_id !== auth.user?.id"
                    size="small"
                  >
                    Я поставил
                  </NTag>
                </div>
                <p class="task-card-title">{{ task.title }}</p>
                <p v-if="task.description" class="task-card-desc">{{ task.description }}</p>
                <p class="task-card-meta task-card__due">
                  <span
                    class="task-card__due-date"
                    :class="{ 'task-card__due-date--overdue': cardIsOverdue(task) }"
                  >
                    Срок: {{ formatDue(task.due_at) }}
                  </span>
                  <span
                    v-if="task.due_at && task.status !== 'closed' && task.status !== 'deleted'"
                    class="task-card__countdown"
                    :class="`task-card__countdown--${deadlineFor(task).tone}`"
                  >
                    {{ deadlineFor(task).text }}
                  </span>
                </p>
                <p class="task-card-meta">
                  Исполнитель: {{ task.assignee?.full_name ?? '—' }}
                </p>
                <p class="task-card-meta">Поставил: {{ task.creator?.full_name ?? 'Старший оператор' }}</p>
                <NButton
                  v-if="canReassignTask(task)"
                  size="small"
                  secondary
                  style="margin-right: 8px"
                  @click.stop="openReassign(task)"
                >
                  Переназначить
                </NButton>
                <NButton
                  v-if="task.status === 'new' && isAssignedToMe(task)"
                  type="primary"
                  size="small"
                  style="margin-right: 8px"
                  @click.stop="onAcknowledge(task)"
                >
                  Принять
                </NButton>
                <NButton
                  v-if="(task.status === 'open' || task.status === 'new') && isAssignedToMe(task)"
                  type="primary"
                  size="small"
                  @click.stop="onComplete(task)"
                >
                  <template #icon><Check :size="14" /></template>
                  Выполнено
                </NButton>
                <NButton
                  v-if="canReviewTask(task)"
                  type="primary"
                  size="small"
                  style="margin-right: 8px"
                  @click.stop="onConfirm(task)"
                >
                  <template #icon><Check :size="14" /></template>
                  Подтвердить
                </NButton>
                <NButton
                  v-if="canReviewTask(task)"
                  size="small"
                  @click.stop="onReopen(task)"
                >
                  <template #icon><RotateCcw :size="14" /></template>
                  Вернуть
                </NButton>
              </div>
            </div>
            <p v-else class="empty-hint">{{ mineEmptyHint }}</p>
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
          />
        </NFormItem>
        <NFormItem label="Исполнитель" required>
          <NSelect
            v-model:value="formAssigneeId"
            :options="assigneeOptions"
            filterable
            placeholder="Любой сотрудник"
          />
        </NFormItem>
        <NFormItem label="Срок выполнения">
          <NDatePicker
            v-model:value="formDueAt"
            type="datetime"
            clearable
            style="width: 100%"
          />
        </NFormItem>
        <NFormItem label="Файлы">
          <NUpload
            :key="formUploadKey"
            multiple
            :default-upload="false"
            @change="onCreateUploadChange"
          >
            <NButton size="small" secondary>Прикрепить файлы</NButton>
          </NUpload>
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
            placeholder="Любой сотрудник"
          />
        </NFormItem>
      </NForm>
      <template #footer>
        <NButton type="primary" :loading="reassignLoading" @click="submitReassign">
          Сохранить
        </NButton>
      </template>
    </NModal>

    <TaskDetailModal
      v-model:show="detailOpen"
      :task-id="detailTaskId"
      @updated="activeTab === 'board' ? loadBoard() : loadMine()"
      @open="onOpenRelatedTask"
    />
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

.task-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
}

.task-filters__closed {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--app-text-muted);
  white-space: nowrap;
}

.task-filters__summary {
  margin: 10px 0 0;
  font-size: 13px;
  color: var(--app-text-muted);
}

.kanban {
  display: grid;
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

.kanban-col--deleted {
  border-color: color-mix(in srgb, var(--app-danger, #dc2626) 35%, var(--app-border));
}

.kanban-col-dot--closed {
  background: var(--app-success);
}

.kanban-col-dot--deleted {
  background: var(--app-danger, #dc2626);
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

.mine-buckets {
  margin: 4px 0 16px;
  max-width: 640px;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 640px;
}

.task-card {
  border: 1px solid var(--app-border);
  border-left-width: 3px;
  border-radius: var(--app-control-radius);
  padding: 12px;
  background: var(--app-surface);
}

.task-card--new {
  border-left-color: var(--app-warning);
}

.task-card--open {
  border-left-color: var(--app-accent);
}

.task-card--done_pending {
  border-left-color: var(--app-warning);
}

.task-card--closed {
  border-left-color: var(--app-success);
}

.task-card--deleted {
  border-left-color: var(--app-danger);
}

.task-card--due-soon {
  background: color-mix(in srgb, var(--app-warning) 10%, var(--app-surface));
}

.task-card--overdue {
  background: var(--app-danger-soft);
  border-color: color-mix(in srgb, var(--app-danger) 55%, var(--app-border));
  border-left-width: 4px;
  border-left-color: var(--app-danger);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--app-danger) 18%, transparent);
}

.task-card--clickable {
  cursor: pointer;
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

.task-card--overdue:hover {
  border-color: var(--app-danger);
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

.task-card__due {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
}

.task-card__due-date--overdue {
  color: var(--app-danger);
  font-weight: 700;
}

.task-card__countdown {
  font-weight: 700;
  font-size: 12px;
  white-space: nowrap;
}

.task-card__countdown--overdue {
  color: var(--app-danger);
}

.task-card__countdown--soon {
  color: var(--app-warning);
}

.task-card__countdown--ok {
  color: var(--app-text-muted);
  font-weight: 600;
}

.task-card-actions {
  margin-top: 10px;
}
</style>
