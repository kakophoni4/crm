<script setup lang="ts">
import {
  NButton,
  NEmpty,
  NInput,
  NModal,
  NSpace,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import { Download, Eye } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import {
  addTaskComment,
  getTask,
  notifyTaskAssignee,
  notifyTaskCreator,
  type DepartmentTask,
  type TaskDetail,
} from '@/features/tasks/api'
import { TASK_TYPE_COLORS, type TaskFileBrief } from '@/features/tasks/types'
import {
  attachmentPreviewSupported,
  resolveAttachmentPreviewKind,
  type AttachmentPreviewKind,
} from '@/shared/lib/attachment-preview-kind'
import { AppError, http } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'
import AttachmentPreviewModal from '@/widgets/chat/AttachmentPreviewModal.vue'

const props = defineProps<{
  show: boolean
  taskId: number | null
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  updated: []
}>()

const message = useMessage()
const auth = useAuthStore()
const loading = ref(false)
const detail = ref<TaskDetail | null>(null)
const commentBody = ref('')
const commentLoading = ref(false)
const notifyLoading = ref<string | null>(null)

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
  return meId.value === task.assignee_id || isManager.value
})

watch(
  () => [props.show, props.taskId] as const,
  ([open, id]) => {
    if (!open || id == null) {
      detail.value = null
      commentBody.value = ''
      closeFilePreview()
      return
    }
    void load(id)
  },
)

async function load(id: number): Promise<void> {
  loading.value = true
  try {
    detail.value = await getTask(id)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось открыть задачу')
    emit('update:show', false)
  } finally {
    loading.value = false
  }
}

async function onAddComment(): Promise<void> {
  if (props.taskId == null || !commentBody.value.trim()) return
  commentLoading.value = true
  try {
    const created = await addTaskComment(props.taskId, commentBody.value.trim())
    commentBody.value = ''
    if (detail.value) {
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

async function downloadFile(fileId: number, name: string): Promise<void> {
  try {
    const { data } = await http.get<Blob>(`/files/${fileId}`, { responseType: 'blob' })
    const url = URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
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
    const { data } = await http.get<Blob>(`/files/${file.id}`, { responseType: 'blob' })
    previewBlob.value = data
    previewBlobUrl.value = URL.createObjectURL(data)
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

function typeColor(task: DepartmentTask): string {
  return TASK_TYPE_COLORS[task.task_type] || '#6b7280'
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    :title="detail ? detail.title : 'Задача'"
    style="width: min(640px, 96vw)"
    @update:show="emit('update:show', $event)"
  >
    <NSpin :show="loading">
      <template v-if="detail">
        <div class="task-detail">
          <NSpace size="small" wrap>
            <NTag :color="{ color: typeColor(detail), textColor: '#fff' }" size="small">
              {{ detail.task_type_label }}
            </NTag>
            <NTag size="small" :bordered="false">{{ detail.status }}</NTag>
            <NTag v-if="detail.is_overdue" type="error" size="small">Просрочена</NTag>
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
              <dd>{{ formatDue(detail.due_at) }}</dd>
            </div>
          </dl>

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
                  <NButton size="tiny" secondary @click="downloadFile(file.id, file.original_name)">
                    <template #icon><Download :size="12" /></template>
                    Скачать
                  </NButton>
                </NSpace>
              </li>
            </ul>
            <NEmpty v-else description="Файлов нет" size="small" />
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
              placeholder="Оставить комментарий"
              style="margin-top: 8px"
            />
            <NButton
              type="primary"
              size="small"
              style="margin-top: 8px"
              :loading="commentLoading"
              :disabled="!commentBody.trim()"
              @click="onAddComment"
            >
              Отправить
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
        <NButton @click="emit('update:show', false)">Закрыть</NButton>
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
.task-detail__desc {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.9rem;
}
.task-detail__files,
.task-detail__comments {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.task-detail__files li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  font-size: 0.85rem;
}
.task-detail__comments li {
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--app-border) 30%, transparent);
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
@media (max-width: 640px) {
  .task-detail__meta {
    grid-template-columns: 1fr;
  }
}
</style>
