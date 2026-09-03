<script setup lang="ts">
import {
  NButton,
  NDatePicker,
  NEmpty,
  NInput,
  NModal,
  NRadio,
  NRadioGroup,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NUpload,
  useDialog,
  useMessage,
} from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { Download, Eye } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import { uploadFile } from '@/features/chats/api'
import {
  addTaskComment,
  attachTaskFiles,
  completeTask,
  confirmTask,
  formatTaskAssigneeLabel,
  getTask,
  getTaskHistory,
  handoffTask,
  reopenTask,
  listTaskAssignees,
  notifyTaskAssignee,
  notifyTaskCreator,
  type DepartmentTask,
  type TaskAssigneeOption,
  type TaskDetail,
  type TaskHistoryItem,
} from '@/features/tasks/api'
import { TASK_TYPE_COLORS, type TaskFileBrief } from '@/features/tasks/types'
import { taskDeadline, taskIsOverdue } from '@/features/tasks/due'
import {
  attachmentPreviewSupported,
  resolveAttachmentPreviewKind,
  type AttachmentPreviewKind,
} from '@/shared/lib/attachment-preview-kind'
import { AppError } from '@/shared/api/http'
import { fetchAttachmentBlob } from '@/shared/lib/attachment-blob-cache'
import { useAuthStore } from '@/shared/store/auth'
import AttachmentPreviewModal from '@/widgets/chat/AttachmentPreviewModal.vue'

const props = defineProps<{
  show: boolean
  taskId: number | null
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  updated: []
  open: [taskId: number]
}>()

const message = useMessage()
const dialog = useDialog()
const auth = useAuthStore()
const loading = ref(false)
const detail = ref<TaskDetail | null>(null)
const historyItems = ref<TaskHistoryItem[]>([])
const historyLoading = ref(false)
const commentBody = ref('')
const commentLoading = ref(false)
const notifyLoading = ref<string | null>(null)
const commentFiles = ref<File[]>([])
const uploadKey = ref(0)
const actionBusy = ref(false)
const completeBusy = ref(false)
const attachBusy = ref(false)
const attachKey = ref(0)
const attachPending = ref<File[]>([])

const handoffUserId = ref<number | null>(null)
const handoffAction = ref<'add' | 'transfer' | 'follow_up'>('add')
const followTitle = ref('')
const followDescription = ref('')
const followDueAt = ref<number | null>(null)
const assigneeUsers = ref<TaskAssigneeOption[]>([])

const previewOpen = ref(false)
const previewLoading = ref(false)
const previewName = ref('')
const previewMime = ref('')
const previewBlob = ref<Blob | null>(null)
const previewBlobUrl = ref<string | null>(null)
const previewKind = computed<AttachmentPreviewKind>(() =>
  previewName.value
    ? resolveAttachmentPreviewKind({ name: previewName.value, mime: previewMime.value })
    : 'unsupported',
)

const meId = computed(() => auth.user?.id ?? null)
const isManager = computed(() => auth.canManageTasks)

const isWorkingOn = computed(() => {
  const task = detail.value
  if (!task || meId.value == null) return false
  if (task.assignee_id === meId.value) return true
  return (task.collaborators ?? []).some((c) => c.id === meId.value)
})

const isActive = computed(() => {
  const status = detail.value?.status
  return status === 'new' || status === 'open' || status === 'done_pending'
})

const isCreator = computed(() => {
  const task = detail.value
  return task != null && meId.value != null && task.created_by === meId.value
})

const canChangeAssignee = computed(
  () => isActive.value && (isCreator.value || isWorkingOn.value || isManager.value),
)

const canReply = computed(() => isWorkingOn.value && isActive.value)
const canAttachFiles = computed(() => {
  const status = detail.value?.status
  return status != null && status !== 'closed' && status !== 'deleted'
})

const canNotifyAssignee = computed(() => {
  const task = detail.value
  if (!task || meId.value == null) return false
  if (meId.value === task.assignee_id && !isManager.value) return false
  return meId.value === task.created_by || isManager.value
})

const canNotifyCreator = computed(() => {
  const task = detail.value
  if (!task || meId.value == null) return false
  if (meId.value === task.created_by && !isManager.value) return false
  return isWorkingOn.value || isManager.value
})

const canReviewCompletion = computed(() => {
  const task = detail.value
  if (!task || task.status !== 'done_pending') return false
  return isCreator.value || isManager.value
})

const assigneeOptions = computed(() =>
  assigneeUsers.value
    .filter((u) => u.id !== detail.value?.assignee_id)
    .map((u) => ({
      label: formatTaskAssigneeLabel(u, meId.value),
      value: u.id,
    })),
)

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    new: 'Новая',
    open: 'В работе',
    done_pending: 'На проверке',
    closed: 'Готово',
    deleted: 'Удалённые',
  }
  return map[detail.value?.status || ''] || detail.value?.status || ''
})

watch(
  () => [props.show, props.taskId] as const,
  ([open, id]) => {
    if (!open || id == null) {
      detail.value = null
      historyItems.value = []
      commentBody.value = ''
      commentFiles.value = []
      uploadKey.value += 1
      handoffUserId.value = null
      handoffAction.value = 'add'
      followTitle.value = ''
      followDescription.value = ''
      followDueAt.value = null
      closeFilePreview()
      return
    }
    void load(id)
    void loadAssignees()
  },
)

async function loadHistory(id: number): Promise<void> {
  historyLoading.value = true
  try {
    historyItems.value = await getTaskHistory(id)
  } catch {
    historyItems.value = []
  } finally {
    historyLoading.value = false
  }
}

async function loadAssignees(): Promise<void> {
  try {
    assigneeUsers.value = await listTaskAssignees()
  } catch {
    assigneeUsers.value = []
  }
}

async function load(id: number): Promise<void> {
  loading.value = true
  try {
    detail.value = await getTask(id)
    void loadHistory(id)
    const me = meId.value
    const working =
      me != null &&
      (detail.value.assignee_id === me ||
        (detail.value.collaborators ?? []).some((c) => c.id === me))
    handoffAction.value = working ? 'add' : 'transfer'
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось открыть задачу')
    emit('update:show', false)
  } finally {
    loading.value = false
  }
}

async function uploadPending(): Promise<number[]> {
  const ids: number[] = []
  for (const file of commentFiles.value) {
    const uploaded = await uploadFile(file)
    ids.push(uploaded.id)
  }
  return ids
}

async function onAddComment(): Promise<void> {
  if (props.taskId == null) return
  if (!commentBody.value.trim() && !commentFiles.value.length) return
  commentLoading.value = true
  try {
    const fileIds = await uploadPending()
    const created = await addTaskComment(props.taskId, commentBody.value.trim(), fileIds)
    commentBody.value = ''
    commentFiles.value = []
    uploadKey.value += 1
    await load(props.taskId)
    if (detail.value && !detail.value.comments.some((c) => c.id === created.id)) {
      detail.value = {
        ...detail.value,
        comments: [...detail.value.comments, created],
      }
    }
    emit('updated')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось отправить комментарий')
  } finally {
    commentLoading.value = false
  }
}

async function onComplete(): Promise<void> {
  if (props.taskId == null) return
  dialog.warning({
    title: 'Отметить выполненной?',
    content: 'Задача уйдёт на проверку постановщику.',
    positiveText: 'Выполнено',
    negativeText: 'Отмена',
    onPositiveClick: async () => {
      completeBusy.value = true
      try {
        const fileIds = await uploadPending()
        await completeTask(props.taskId!, {
          comment: commentBody.value.trim() || null,
          file_ids: fileIds,
        })
        commentBody.value = ''
        commentFiles.value = []
        uploadKey.value += 1
        message.success('Отмечено как выполненное — ждёт подтверждения постановщика')
        await load(props.taskId!)
        emit('updated')
      } catch (err) {
        message.error(err instanceof AppError ? err.message : 'Не удалось отметить выполнение')
      } finally {
        completeBusy.value = false
      }
    },
  })
}

async function onConfirm(): Promise<void> {
  if (props.taskId == null) return
  actionBusy.value = true
  try {
    await confirmTask(props.taskId)
    message.success('Задача подтверждена и закрыта')
    await load(props.taskId)
    emit('updated')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось подтвердить задачу')
  } finally {
    actionBusy.value = false
  }
}

async function onReopen(): Promise<void> {
  if (props.taskId == null) return
  actionBusy.value = true
  try {
    await reopenTask(props.taskId)
    message.info('Задача возвращена исполнителю')
    await load(props.taskId)
    emit('updated')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось вернуть задачу')
  } finally {
    actionBusy.value = false
  }
}

async function onHandoff(): Promise<void> {
  if (props.taskId == null || handoffUserId.value == null) {
    message.warning('Выберите сотрудника')
    return
  }
  if (handoffAction.value === 'follow_up' && !followTitle.value.trim() && !detail.value?.title) {
    message.warning('Укажите название связанной задачи')
    return
  }
  actionBusy.value = true
  try {
    const fileIds = await uploadPending()
    await handoffTask(props.taskId, {
      action: handoffAction.value,
      user_id: handoffUserId.value,
      comment: commentBody.value.trim() || null,
      file_ids: fileIds,
      follow_up_title: followTitle.value.trim() || null,
      follow_up_description: followDescription.value.trim() || null,
      follow_up_due_at: followDueAt.value ? new Date(followDueAt.value).toISOString() : null,
    })
    const done =
      handoffAction.value === 'add'
        ? 'Соисполнитель добавлен'
        : handoffAction.value === 'transfer'
          ? 'Задача передана'
          : 'Связанная задача создана'
    message.success(done)
    commentBody.value = ''
    commentFiles.value = []
    uploadKey.value += 1
    followTitle.value = ''
    followDescription.value = ''
    followDueAt.value = null
    handoffUserId.value = null
    await load(props.taskId)
    emit('updated')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось выполнить действие')
  } finally {
    actionBusy.value = false
  }
}

function onAttachSelect(options: { fileList: UploadFileInfo[] }): void {
  attachPending.value = options.fileList
    .map((item) => item.file)
    .filter((file): file is File => file instanceof File)
}

async function submitAttachFiles(): Promise<void> {
  if (props.taskId == null || !canAttachFiles.value || !attachPending.value.length) return
  attachBusy.value = true
  try {
    const ids: number[] = []
    for (const file of attachPending.value) {
      const uploaded = await uploadFile(file)
      ids.push(uploaded.id)
    }
    await attachTaskFiles(props.taskId, ids)
    attachPending.value = []
    attachKey.value += 1
    await load(props.taskId)
    emit('updated')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось прикрепить файл')
  } finally {
    attachBusy.value = false
  }
}

function onUploadChange(options: { fileList: UploadFileInfo[] }): void {
  commentFiles.value = options.fileList
    .map((f) => f.file)
    .filter((f): f is File => f instanceof File)
}

async function onNotifyAssignee(): Promise<void> {
  if (props.taskId == null) return
  notifyLoading.value = 'assignee'
  try {
    await notifyTaskAssignee(props.taskId)
    message.success('Исполнитель уведомлён')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось уведомить')
  } finally {
    notifyLoading.value = null
  }
}

async function onNotifyCreator(): Promise<void> {
  if (props.taskId == null) return
  notifyLoading.value = 'creator'
  try {
    await notifyTaskCreator(props.taskId)
    message.success('Постановщик уведомлён')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось уведомить')
  } finally {
    notifyLoading.value = null
  }
}

async function downloadFile(fileId: number, name: string, mime?: string | null): Promise<void> {
  try {
    const entry = await fetchAttachmentBlob(`/files/${fileId}`, mime)
    const a = document.createElement('a')
    a.href = entry.url
    a.download = name
    a.click()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось скачать файл')
  }
}

function canPreviewFile(file: TaskFileBrief): boolean {
  return attachmentPreviewSupported(
    resolveAttachmentPreviewKind({ name: file.original_name, mime: file.mime_type }),
  )
}

function resetPreviewBlob(): void {
  if (previewBlobUrl.value) URL.revokeObjectURL(previewBlobUrl.value)
  previewBlobUrl.value = null
  previewBlob.value = null
}

async function openFilePreview(file: TaskFileBrief): Promise<void> {
  if (!canPreviewFile(file)) {
    message.warning('Просмотр этого типа файла не поддерживается')
    return
  }
  resetPreviewBlob()
  previewName.value = file.original_name
  previewMime.value = file.mime_type || ''
  previewOpen.value = true
  previewLoading.value = true
  try {
    const entry = await fetchAttachmentBlob(`/files/${file.id}`, file.mime_type)
    previewBlob.value = entry.blob
    previewBlobUrl.value = URL.createObjectURL(entry.blob)
  } catch (err) {
    previewOpen.value = false
    message.error(err instanceof AppError ? err.message : 'Не удалось открыть файл')
  } finally {
    previewLoading.value = false
  }
}

function closeFilePreview(): void {
  previewOpen.value = false
  resetPreviewBlob()
}

function formatDue(iso: string | null): string {
  if (!iso) return 'без срока'
  return new Date(iso).toLocaleString('ru-RU')
}

function deadlineLabel(iso: string | null): string {
  if (!iso) return ''
  return taskDeadline(iso).text
}

function deadlineTone(iso: string | null): string {
  if (!iso) return 'none'
  return taskDeadline(iso).tone
}

function typeColor(task: DepartmentTask): string {
  return TASK_TYPE_COLORS[task.task_type] || '#6b7280'
}

function openChild(id: number): void {
  emit('open', id)
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    :title="detail ? detail.title : 'Задача'"
    style="width: min(720px, 96vw)"
    @update:show="emit('update:show', $event)"
  >
    <NSpin :show="loading">
      <template v-if="detail">
        <div
          class="task-detail"
          :class="{ 'task-detail--overdue': detail && taskIsOverdue(detail) }"
        >
          <NSpace size="small" wrap>
            <NTag :color="{ color: typeColor(detail), textColor: '#fff' }" size="small">
              {{ detail.task_type_label }}
            </NTag>
            <NTag size="small" :bordered="false">{{ statusLabel }}</NTag>
            <NTag v-if="taskIsOverdue(detail)" type="error">Просрочена</NTag>
          </NSpace>

          <dl class="task-detail__meta">
            <div>
              <dt>Постановщик</dt>
              <dd>{{ detail.creator?.full_name || '—' }}</dd>
            </div>
            <div>
              <dt>Исполнитель</dt>
              <dd>{{ detail.assignee?.full_name || '—' }}</dd>
            </div>
            <div>
              <dt>Срок</dt>
              <dd
                class="task-detail__due"
                :class="{ 'task-detail__due--overdue': taskIsOverdue(detail) }"
              >
                {{ formatDue(detail.due_at) }}
                <span
                  v-if="detail.due_at && detail.status !== 'closed' && detail.status !== 'deleted'"
                  class="task-detail__countdown"
                  :class="`task-detail__countdown--${deadlineTone(detail.due_at)}`"
                >
                  {{ deadlineLabel(detail.due_at) }}
                </span>
              </dd>
            </div>
          </dl>

          <p v-if="detail.collaborators?.length" class="task-detail__collab">
            Соисполнители:
            {{ detail.collaborators.map((c) => c.full_name).join(', ') }}
          </p>

          <section>
            <h4>Описание</h4>
            <p v-if="detail.description" class="task-detail__desc">{{ detail.description }}</p>
            <NEmpty v-else description="Без описания" size="small" />
          </section>

          <section>
            <h4>Файлы</h4>
            <ul v-if="detail.files?.length" class="task-detail__files">
              <li v-for="file in detail.files" :key="file.id">
                <span>{{ file.original_name }}</span>
                <NSpace size="small">
                  <NButton
                    v-if="canPreviewFile(file)"
                    size="tiny"
                    secondary
                    @click="openFilePreview(file)"
                  >
                    <template #icon><Eye :size="12" /></template>
                    Просмотр
                  </NButton>
                  <NButton size="tiny" secondary @click="downloadFile(file.id, file.original_name, file.mime_type)">
                    <template #icon><Download :size="12" /></template>
                    Скачать
                  </NButton>
                </NSpace>
              </li>
            </ul>
            <NEmpty v-else description="Файлов нет" size="small" />
            <template v-if="canAttachFiles">
              <NUpload
                :key="attachKey"
                multiple
                :default-upload="false"
                style="margin-top: 8px"
                @change="onAttachSelect"
              >
                <NButton size="small" secondary>Выбрать файлы</NButton>
              </NUpload>
              <NButton
                v-if="attachPending.length"
                size="small"
                type="primary"
                style="margin-top: 8px"
                :loading="attachBusy"
                @click="submitAttachFiles"
              >
                Добавить к задаче
              </NButton>
            </template>
          </section>

          <section v-if="detail.child_tasks?.length">
            <h4>Связанные задачи</h4>
            <ul class="task-detail__children">
              <li v-for="child in detail.child_tasks" :key="child.id">
                <button type="button" class="task-detail__child-btn" @click="openChild(child.id)">
                  {{ child.title }}
                </button>
                <span>{{ child.assignee?.full_name || '—' }} · {{ child.status }}</span>
              </li>
            </ul>
          </section>

          <section>
            <h4>История изменений</h4>
            <NSpin :show="historyLoading" size="small">
              <ul v-if="historyItems.length" class="task-detail__history">
                <li v-for="item in historyItems" :key="item.id">
                  <strong>{{ item.actor?.full_name || 'Система' }}</strong>
                  <p>{{ item.summary }}</p>
                  <span>{{ new Date(item.created_at).toLocaleString('ru-RU') }}</span>
                </li>
              </ul>
            </NSpin>
          </section>

          <section>
            <h4>Комментарии</h4>
            <ul v-if="detail.comments.length" class="task-detail__comments">
              <li v-for="c in detail.comments" :key="c.id">
                <strong>{{ c.author?.full_name || `user #${c.author_id}` }}</strong>
                <p>{{ c.body }}</p>
                <span>{{ new Date(c.created_at).toLocaleString('ru-RU') }}</span>
              </li>
            </ul>
            <NEmpty v-else description="Комментариев пока нет" size="small" />
            <NInput
              v-model:value="commentBody"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              placeholder="Комментарий к ответу"
              style="margin-top: 8px"
            />
            <NUpload
              :key="uploadKey"
              multiple
              :default-upload="false"
              style="margin-top: 8px"
              @change="onUploadChange"
            >
              <NButton size="small" secondary>Прикрепить файлы</NButton>
            </NUpload>
            <NSpace style="margin-top: 8px" wrap>
              <NButton
                type="primary"
                size="small"
                :loading="commentLoading"
                :disabled="!commentBody.trim() && !commentFiles.length"
                @click="onAddComment"
              >
                Отправить комментарий
              </NButton>
              <NButton
                v-if="canReply && detail.status !== 'done_pending'"
                size="small"
                :loading="completeBusy"
                @click="onComplete"
              >
                Отметить выполненным
              </NButton>
            </NSpace>
          </section>

          <section v-if="canChangeAssignee" class="task-detail__handoff">
            <h4>{{ isWorkingOn ? 'Если свою часть сделали' : 'Сменить исполнителя' }}</h4>
            <NRadioGroup v-model:value="handoffAction" name="handoff" style="margin-bottom: 8px">
              <NSpace>
                <NRadio value="add">Добавить соисполнителя</NRadio>
                <NRadio value="transfer">Передать задачу</NRadio>
                <NRadio value="follow_up">Связанная задача</NRadio>
              </NSpace>
            </NRadioGroup>
            <NSelect
              v-model:value="handoffUserId"
              :options="assigneeOptions"
              filterable
              placeholder="Сотрудник"
            />
            <template v-if="handoffAction === 'follow_up'">
              <NInput
                v-model:value="followTitle"
                maxlength="512"
                placeholder="Название связанной задачи"
                style="margin-top: 8px"
              />
              <NInput
                v-model:value="followDescription"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
                placeholder="Что нужно сделать дальше"
                style="margin-top: 8px"
              />
              <NDatePicker
                v-model:value="followDueAt"
                type="datetime"
                clearable
                style="width: 100%; margin-top: 8px"
              />
            </template>
            <NButton
              type="primary"
              style="margin-top: 10px"
              :loading="actionBusy"
              :disabled="handoffUserId == null"
              @click="onHandoff"
            >
              {{
                handoffAction === 'add'
                  ? 'Добавить соисполнителя'
                  : handoffAction === 'transfer'
                    ? 'Передать задачу'
                    : 'Поставить связанную задачу'
              }}
            </NButton>
          </section>
        </div>
      </template>
    </NSpin>

    <template #footer>
      <NSpace justify="space-between" style="width: 100%">
        <NSpace>
          <NButton
            v-if="canNotifyAssignee"
            secondary
            :loading="notifyLoading === 'assignee'"
            @click="onNotifyAssignee"
          >
            Оповестить исполнителя
          </NButton>
          <NButton
            v-if="canNotifyCreator"
            secondary
            :loading="notifyLoading === 'creator'"
            @click="onNotifyCreator"
          >
            Оповестить постановщика
          </NButton>
        </NSpace>
        <NSpace>
          <NButton
            v-if="canReviewCompletion"
            type="primary"
            :loading="actionBusy"
            @click="onConfirm"
          >
            Подтвердить
          </NButton>
          <NButton
            v-if="canReviewCompletion"
            :loading="actionBusy"
            @click="onReopen"
          >
            Вернуть в работу
          </NButton>
          <NButton @click="emit('update:show', false)">Закрыть</NButton>
        </NSpace>
      </NSpace>
    </template>
  </NModal>

  <AttachmentPreviewModal
    :open="previewOpen"
    :loading="previewLoading"
    :label="previewName"
    :blob-url="previewBlobUrl"
    :blob="previewBlob"
    :preview-kind="previewKind"
    @close="closeFilePreview"
  />
</template>

<style scoped>
.task-detail {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.task-detail--overdue {
  padding: 12px;
  margin: -4px;
  border-radius: 10px;
  background: var(--app-danger-soft);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--app-danger) 28%, transparent);
}
.task-detail h4 {
  margin: 0 0 6px;
  font-size: 0.88rem;
}
.task-detail__meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}
.task-detail__meta dt {
  font-size: 0.72rem;
  color: var(--app-text-muted);
}
.task-detail__meta dd {
  margin: 2px 0 0;
  font-size: 0.88rem;
  font-weight: 600;
}
.task-detail__due {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.task-detail__due--overdue {
  color: var(--app-danger);
}
.task-detail__countdown {
  font-size: 0.78rem;
  font-weight: 700;
}
.task-detail__countdown--overdue {
  color: var(--app-danger);
}
.task-detail__countdown--soon {
  color: var(--app-warning);
}
.task-detail__countdown--ok {
  color: var(--app-text-muted);
  font-weight: 600;
}
.task-detail__collab {
  margin: 0;
  font-size: 0.82rem;
  color: var(--app-text-muted);
}
.task-detail__desc {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.9rem;
}
.task-detail__files,
.task-detail__comments,
.task-detail__history,
.task-detail__children {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.task-detail__files li,
.task-detail__children li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  font-size: 0.85rem;
}
.task-detail__child-btn {
  border: 0;
  background: none;
  padding: 0;
  color: var(--app-primary, #2563eb);
  cursor: pointer;
  font: inherit;
  text-align: left;
}
.task-detail__history li,
.task-detail__comments li {
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--app-border) 30%, transparent);
}
.task-detail__history p {
  margin: 4px 0;
  font-size: 0.88rem;
}
.task-detail__history span {
  font-size: 0.72rem;
  color: var(--app-text-muted);
}
.task-detail__comments p {
  margin: 4px 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.88rem;
}
.task-detail__comments span {
  font-size: 0.72rem;
  color: var(--app-text-muted);
}
.task-detail__handoff {
  padding-top: 4px;
  border-top: 1px solid var(--app-border);
}
@media (max-width: 640px) {
  .task-detail__meta {
    grid-template-columns: 1fr;
  }
}
</style>
