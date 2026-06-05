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
  NSwitch,
  useMessage,
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'

import type { BotItem, Department } from '@/features/admin/api'
import {
  createBot,
  listBots,
  listDepartments,
  rotateBotSecret,
  updateBot,
} from '@/features/admin/api'
import { AppError } from '@/shared/api/http'

const message = useMessage()
const loading = ref(false)
const rows = ref<BotItem[]>([])
const departments = ref<Department[]>([])
const showModal = ref(false)
const showEditModal = ref(false)
const secretsModal = ref(false)
const lastSecrets = ref('')
const editingBot = ref<BotItem | null>(null)
const form = ref({
  code: '',
  name: '',
  department_id: null as number | null,
  outbound_url: 'https://example.com/outbound',
  inbound_secret: '',
  outbound_secret: '',
})
const editForm = ref({
  name: '',
  department_id: null as number | null,
  is_active: true,
})

function randomSecret(): string {
  const bytes = new Uint8Array(24)
  crypto.getRandomValues(bytes)
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').slice(0, 32)
}

const departmentOptions = computed<SelectOption[]>(() =>
  departments.value.map((d) => ({ label: d.name, value: d.id })),
)

const columns = computed<DataTableColumns<BotItem>>(() => [
  { title: 'Код', key: 'code', width: 140 },
  { title: 'Название', key: 'name' },
  {
    title: 'Отдел',
    key: 'department_name',
    width: 160,
    render: (row) => row.department_name ?? `#${row.department_id}`,
  },
  {
    title: 'Распределение',
    key: 'owner_label',
    minWidth: 220,
    render: (row) => row.owner_label,
  },
  {
    title: 'Активен',
    key: 'is_active',
    width: 90,
    render: (row) => (row.is_active ? 'да' : 'нет'),
  },
  {
    title: '',
    key: 'actions',
    width: 420,
    render: (row) =>
      h(NSpace, null, () => [
        h(
          NButton,
          { size: 'small', onClick: () => openEdit(row) },
          { default: () => 'Изменить' },
        ),
        h(
          NButton,
          { size: 'small', onClick: () => onRotate(row, 'inbound') },
          { default: () => 'Обновить входящий ключ' },
        ),
        h(
          NButton,
          { size: 'small', onClick: () => onRotate(row, 'outbound') },
          { default: () => 'Обновить исходящий ключ' },
        ),
      ]),
  },
])

function openCreate(): void {
  form.value = {
    code: '',
    name: '',
    department_id: departments.value[0]?.id ?? null,
    outbound_url: 'https://example.com/outbound',
    inbound_secret: randomSecret(),
    outbound_secret: randomSecret(),
  }
  showModal.value = true
}

function openEdit(row: BotItem): void {
  editingBot.value = row
  editForm.value = {
    name: row.name,
    department_id: row.department_id,
    is_active: row.is_active,
  }
  showEditModal.value = true
}

async function load(): Promise<void> {
  loading.value = true
  try {
    departments.value = await listDepartments()
    rows.value = await listBots()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить ботов')
  } finally {
    loading.value = false
  }
}

async function onSave(): Promise<void> {
  if (!form.value.code.trim() || !form.value.name.trim()) {
    message.warning('Заполните код и название')
    return
  }
  if (form.value.department_id == null) {
    message.warning('Выберите отдел')
    return
  }
  if (form.value.inbound_secret.length < 16 || form.value.outbound_secret.length < 16) {
    message.warning('Секреты должны быть не короче 16 символов')
    return
  }
  try {
    const created = await createBot({
      code: form.value.code.trim(),
      name: form.value.name.trim(),
      department_id: form.value.department_id,
      outbound_url: form.value.outbound_url.trim(),
      inbound_secret: form.value.inbound_secret,
      outbound_secret: form.value.outbound_secret,
    })
    showModal.value = false
    if (created.secrets) {
      lastSecrets.value = `inbound: ${created.secrets.inbound_secret}\noutbound: ${created.secrets.outbound_secret}\n\n${created.secrets.warning}`
      secretsModal.value = true
    }
    message.success('Бот создан')
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка создания')
  }
}

async function onSaveEdit(): Promise<void> {
  const bot = editingBot.value
  if (!bot) return
  if (!editForm.value.name.trim()) {
    message.warning('Укажите название')
    return
  }
  if (editForm.value.department_id == null) {
    message.warning('Выберите отдел')
    return
  }
  try {
    await updateBot(bot.id, {
      name: editForm.value.name.trim(),
      department_id: editForm.value.department_id,
      is_active: editForm.value.is_active,
    })
    showEditModal.value = false
    editingBot.value = null
    message.success('Бот обновлён')
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка сохранения')
  }
}

async function onRotate(row: BotItem, kind: 'inbound' | 'outbound'): Promise<void> {
  try {
    const { secret } = await rotateBotSecret(row.id, kind)
    lastSecrets.value = `${kind}: ${secret}`
    secretsModal.value = true
    message.success('Секрет обновлён')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка ротации')
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="admin-page">
    <header class="admin-page__header">
      <div>
        <h1 class="admin-page__title">Боты</h1>
        <p class="admin-page__hint">
          Админ привязывает бота к отделу. Старший распределяет бота по группам внутри отдела.
        </p>
      </div>
      <NButton type="primary" @click="openCreate">Создать бота</NButton>
    </header>
    <NSpin :show="loading">
      <NDataTable :columns="columns" :data="rows" :row-key="(r: BotItem) => r.id" />
    </NSpin>

    <NModal
      v-model:show="showModal"
      preset="card"
      title="Новый бот"
      style="max-width: 520px"
    >
      <NForm label-placement="top">
        <NFormItem label="Код">
          <NInput v-model:value="form.code" />
        </NFormItem>
        <NFormItem label="Название">
          <NInput v-model:value="form.name" />
        </NFormItem>
        <NFormItem label="Отдел">
          <NSelect
            v-model:value="form.department_id"
            :options="departmentOptions"
            placeholder="Выберите отдел…"
          />
        </NFormItem>
        <NFormItem label="URL исходящих событий">
          <NInput v-model:value="form.outbound_url" />
        </NFormItem>
        <NFormItem label="Входящий секрет (inbound)">
          <NInput v-model:value="form.inbound_secret" type="password" show-password-on="click" />
        </NFormItem>
        <NFormItem label="Исходящий секрет (outbound)">
          <NInput v-model:value="form.outbound_secret" type="password" show-password-on="click" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showModal = false">Отмена</NButton>
          <NButton type="primary" @click="onSave">Создать</NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal
      v-model:show="showEditModal"
      preset="card"
      title="Изменить бота"
      style="max-width: 520px"
    >
      <NForm label-placement="top">
        <NFormItem label="Код">
          <NInput :value="editingBot?.code ?? ''" disabled />
        </NFormItem>
        <NFormItem label="Название">
          <NInput v-model:value="editForm.name" />
        </NFormItem>
        <NFormItem label="Отдел">
          <NSelect
            v-model:value="editForm.department_id"
            :options="departmentOptions"
            placeholder="Выберите отдел…"
          />
        </NFormItem>
        <NFormItem label="Активен">
          <NSwitch v-model:value="editForm.is_active" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showEditModal = false">Отмена</NButton>
          <NButton type="primary" @click="onSaveEdit">Сохранить</NButton>
        </NSpace>
      </template>
    </NModal>

    <NModal v-model:show="secretsModal" preset="card" title="Секреты (сохраните сейчас)">
      <pre class="admin-page__secrets">{{ lastSecrets }}</pre>
    </NModal>
  </section>
</template>

<style scoped>
.admin-page__header {
  display: flex;
  align-items: flex-start;
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
  margin: 6px 0 0;
  color: var(--app-text-muted);
  font-size: 0.875rem;
}

.admin-page__secrets {
  white-space: pre-wrap;
  font-size: 0.85rem;
  margin: 0;
}
</style>
