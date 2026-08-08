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

import { uploadFile } from '@/features/chats/api'
import type { Chat } from '@/features/chats/types'
import {
  createClientRequirement,
  listClientRequirementUnits,
  listClientRequirementsByChat,
  type DepartmentTask,
} from '@/features/tasks/api'
import { AppError } from '@/shared/api/http'

const props = defineProps<{
  chat: Chat
}>()

const message = useMessage()
const loading = ref(false)
const submitting = ref(false)
const units = ref<{ id: number; inn: string; name: string }[]>([])
const items = ref<DepartmentTask[]>([])
const unitId = ref<number | null>(null)
const title = ref('')
const description = ref('')
const dueAt = ref<number | null>(null)
const pendingFiles = ref<File[]>([])

const unitOptions = computed(() =>
  units.value.map((u) => ({
    label: `${u.name} (${u.inn})`,
    value: u.id,
  })),
)

async function load(): Promise<void> {
  loading.value = true
  try {
    const [unitRows, list] = await Promise.all([
      listClientRequirementUnits(),
      listClientRequirementsByChat(props.chat.id),
    ])
    units.value = unitRows
    items.value = list.items
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.chat.id,
  () => {
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
      title: title.value.trim(),
      description: description.value.trim() || null,
      due_at: dueAt.value ? new Date(dueAt.value).toISOString() : null,
      file_ids: fileIds,
      chat_id: props.chat.id,
      lead_id: null,
    })
    message.success('Отправлено бухгалтеру лавки')
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
    <p class="client-req__hint">
      Выберите лавку — задача уйдёт бухгалтеру, привязанному к этой ООО.
    </p>
    <NSpin :show="loading">
      <NForm label-placement="top" size="small">
        <NFormItem label="Лавка (ООО)" required>
          <NSelect
            v-model:value="unitId"
            :options="unitOptions"
            filterable
            placeholder="Выберите лавку"
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
          Отправить бухгалтеру
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
.client-req__hint {
  margin: 0;
  font-size: 0.82rem;
  color: var(--n-text-color-3);
  line-height: 1.35;
}
.client-req__list {
  margin-top: 16px;
  border-top: 1px solid var(--n-border-color);
  padding-top: 12px;
}
.client-req__list-title {
  margin: 0 0 8px;
  font-size: 0.9rem;
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
  padding: 8px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--n-border-color) 70%, transparent);
}
.client-req__item-title {
  font-weight: 560;
  margin-bottom: 4px;
}
.client-req__meta {
  font-size: 0.75rem;
  color: var(--n-text-color-3);
}
</style>
