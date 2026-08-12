<script setup lang="ts">
import {
  NButton,
  NDatePicker,
  NEmpty,
  NForm,
  NFormItem,
  NInput,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NUpload,
  useMessage,
} from 'naive-ui'
import type { UploadFileInfo } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import type { ChatDetail } from '@/entities/chat/types'
import { uploadFile } from '@/features/chats/api'
import {
  createClientRequirement,
  formatTaskAssigneeLabel,
  listClientRequirementUnits,
  listClientRequirementsByChat,
  type DepartmentTask,
} from '@/features/tasks/api'
import { AppError } from '@/shared/api/http'
import { lavkaLabel } from '@/shared/lib/lavka-name'

const props = defineProps<{
  chat: ChatDetail
}>()

const message = useMessage()
const loading = ref(false)
const submitting = ref(false)
const units = ref<
  { id: number; inn: string; name: string; accountant_user_id?: number | null }[]
>([])
const accountants = ref<{ id: number; full_name: string; role?: string }[]>([])
const items = ref<DepartmentTask[]>([])
const unitId = ref<number | null>(null)
const assigneeId = ref<number | null>(null)
/** True after manager manually picks an accountant — unit change won't overwrite. */
const assigneeTouched = ref(false)
const title = ref('')
const description = ref('')
const dueAt = ref<number | null>(null)
const pendingFiles = ref<File[]>([])

const unitOptions = computed(() =>
  units.value.map((u) => ({
    label: lavkaLabel(u.name, u.inn),
    value: u.id,
    title: `${u.name} · ${u.inn}`,
  })),
)

const accountantOptions = computed(() =>
  accountants.value.map((a) => ({
    label: formatTaskAssigneeLabel(a),
    value: a.id,
  })),
)

function suggestAccountantForUnit(nextUnitId: number | null): void {
  if (assigneeTouched.value || nextUnitId == null) return
  const unit = units.value.find((u) => u.id === nextUnitId)
  if (unit?.accountant_user_id != null) {
    assigneeId.value = unit.accountant_user_id
  }
}

function onUnitChange(value: number | null): void {
  unitId.value = value
  suggestAccountantForUnit(value)
}

function onAssigneeChange(value: number | null): void {
  assigneeId.value = value
  assigneeTouched.value = value != null
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [unitsPayload, list] = await Promise.all([
      listClientRequirementUnits(),
      listClientRequirementsByChat(props.chat.id),
    ])
    units.value = unitsPayload.items
    accountants.value = unitsPayload.assignees?.length
      ? unitsPayload.assignees
      : unitsPayload.accountants
    items.value = list.items
    suggestAccountantForUnit(unitId.value)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.chat.id,
  () => {
    unitId.value = null
    assigneeId.value = null
    assigneeTouched.value = false
    title.value = ''
    description.value = ''
    dueAt.value = null
    pendingFiles.value = []
    void load()
  },
  { immediate: true },
)

function onUploadChange(options: { fileList: UploadFileInfo[] }): void {
  pendingFiles.value = options.fileList
    .map((f) => f.file)
    .filter((f): f is File => f instanceof File)
}

async function onSubmit(): Promise<void> {
  if (unitId.value == null) {
    message.warning('Выберите лавку')
    return
  }
  if (assigneeId.value == null) {
    message.warning('Выберите исполнителя')
    return
  }
  if (!title.value.trim()) {
    message.warning('Укажите текст требования')
    return
  }
  submitting.value = true
  try {
    const fileIds: number[] = []
    for (const file of pendingFiles.value) {
      const uploaded = await uploadFile(file)
      fileIds.push(uploaded.id)
    }
    await createClientRequirement({
      unit_id: unitId.value,
      assignee_id: assigneeId.value,
      title: title.value.trim(),
      description: description.value.trim() || null,
      due_at: dueAt.value ? new Date(dueAt.value).toISOString() : null,
      file_ids: fileIds,
      chat_id: props.chat.id,
      lead_id: null,
    })
    message.success('Задача отправлена')
    title.value = ''
    description.value = ''
    dueAt.value = null
    pendingFiles.value = []
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось отправить')
  } finally {
    submitting.value = false
  }
}

function statusLabel(status: string): string {
  if (status === 'new') return 'Новая'
  if (status === 'open') return 'В работе'
  if (status === 'done_pending') return 'На проверке'
  if (status === 'closed') return 'Готово'
  return status
}
</script>

<template>
  <div class="client-req">
    <h2 class="client-req__title">Требование от клиента</h2>
    <NSpin :show="loading">
      <NForm label-placement="top" size="small">
        <NFormItem label="Лавка (ООО)" required>
          <NSelect
            :value="unitId"
            :options="unitOptions"
            filterable
            placeholder="Выберите лавку"
            :consistent-menu-width="false"
            @update:value="onUnitChange"
          />
        </NFormItem>
        <NFormItem label="Исполнитель" required>
          <NSelect
            :value="assigneeId"
            :options="accountantOptions"
            filterable
            clearable
            placeholder="Любой сотрудник"
            @update:value="onAssigneeChange"
          />
        </NFormItem>
        <NFormItem label="Заголовок" required>
          <NInput v-model:value="title" placeholder="Кратко: что нужно от бухгалтерии" />
        </NFormItem>
        <NFormItem label="Описание">
          <NInput
            v-model:value="description"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 6 }"
            placeholder="Детали требования от клиента"
          />
        </NFormItem>
        <NFormItem label="Срок">
          <NDatePicker v-model:value="dueAt" type="datetime" clearable style="width: 100%" />
        </NFormItem>
        <NFormItem label="Файлы">
          <NUpload multiple :default-upload="false" @change="onUploadChange">
            <NButton size="small" secondary>Прикрепить</NButton>
          </NUpload>
        </NFormItem>
        <NButton type="primary" block :loading="submitting" @click="onSubmit">
          Отправить задачу
        </NButton>
      </NForm>

      <div class="client-req__list">
        <h3 class="client-req__list-title">Отправленные</h3>
        <NEmpty v-if="!items.length && !loading" description="Пока нет отправленных требований" />
        <ul v-else class="client-req__items">
          <li v-for="row in items" :key="row.id" class="client-req__item">
            <div class="client-req__item-title">{{ row.title }}</div>
            <NSpace :size="6" align="center">
              <NTag size="tiny" :bordered="false">{{ statusLabel(row.status) }}</NTag>
              <span v-if="row.due_at" class="client-req__meta">
                до {{ new Date(row.due_at).toLocaleString('ru-RU') }}
              </span>
            </NSpace>
          </li>
        </ul>
      </div>
    </NSpin>
  </div>
</template>

<style scoped>
.client-req {
  padding: 12px 14px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  overflow: auto;
}
.client-req__title {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 650;
}
.client-req__list {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--app-border);
}
.client-req__list-title {
  margin: 0 0 8px;
  font-size: 0.9rem;
  font-weight: 600;
}
.client-req__items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.client-req__item {
  padding: 8px 10px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-bg, transparent);
}
.client-req__item-title {
  font-size: 0.88rem;
  font-weight: 600;
  margin-bottom: 4px;
  word-break: break-word;
}
.client-req__meta {
  font-size: 0.75rem;
  color: var(--app-text-muted);
}
</style>
