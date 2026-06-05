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
  useMessage,
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'

import type { BotItem, Department, Group } from '@/features/admin/api'
import {
  createBot,
  listBots,
  listDepartments,
  listGroups,
  rotateBotSecret,
} from '@/features/admin/api'
import { AppError } from '@/shared/api/http'

const message = useMessage()
const loading = ref(false)
const rows = ref<BotItem[]>([])
const departments = ref<Department[]>([])
const groups = ref<Group[]>([])
const showModal = ref(false)
const secretsModal = ref(false)
const lastSecrets = ref('')
const form = ref({
  code: '',
  name: '',
  ownerId: '' as string,
  outbound_url: 'https://example.com/outbound',
  inbound_secret: '',
  outbound_secret: '',
})

function randomSecret(): string {
  const bytes = new Uint8Array(24)
  crypto.getRandomValues(bytes)
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').slice(0, 32)
}

const ownerOptions = computed<SelectOption[]>(() => [
  ...departments.value.map((d) => ({ label: 'Отдел: ' + d.name, value: 'dept_' + d.id })),
  ...groups.value.map((g) => ({ label: 'Группа: ' + g.name, value: 'grp_' + g.id })),
])

function ownerLabel(row: BotItem): string {
  if (row.owner_type === 'department') {
    const dept = departments.value.find((d) => d.id === row.owner_id)
    return 'Отдел: ' + (dept?.name ?? String(row.owner_id))
  }
  const grp = groups.value.find((g) => g.id === row.owner_id)
  return 'Группа: ' + (grp?.name ?? String(row.owner_id))
}

const columns = computed<DataTableColumns<BotItem>>(() => [
  { title: 'Код', key: 'code', width: 140 },
  { title: 'Название', key: 'name' },
  {
    title: 'Владелец',
    key: 'owner_id',
    width: 200,
    render: (row) => ownerLabel(row),
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
    width: 360,
    render: (row) =>
      h(NSpace, null, () => [
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
    ownerId: '',
    outbound_url: 'https://example.com/outbound',
    inbound_secret: randomSecret(),
    outbound_secret: randomSecret(),
  }
  showModal.value = true
}

async function load(): Promise<void> {
  loading.value = true
  try {
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
  if (!form.value.ownerId) {
    message.warning('Выберите владельца')
    return
  }
  if (form.value.inbound_secret.length < 16 || form.value.outbound_secret.length < 16) {
    message.warning('Секреты должны быть не короче 16 символов')
    return
  }
  const [prefix, idStr] = form.value.ownerId.split('_')
  const owner_type = prefix === 'dept' ? 'department' : 'group'
  const owner_id = Number(idStr)
  try {
    const created = await createBot({
      code: form.value.code.trim(),
      name: form.value.name.trim(),
      owner_type,
      owner_id,
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

onMounted(async () => {
  ;[departments.value, groups.value] = await Promise.all([listDepartments(), listGroups()])
  await load()
})
</script>

<template>
  <section class="admin-page">
    <header class="admin-page__header">
      <h1 class="admin-page__title">Боты</h1>
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
        <NFormItem label="Владелец (отдел или группа)">
          <NSelect
            v-model:value="form.ownerId"
            :options="ownerOptions"
            placeholder="Выберите…"
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

    <NModal v-model:show="secretsModal" preset="card" title="Секреты (сохраните сейчас)">
      <pre class="admin-page__secrets">{{ lastSecrets }}</pre>
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

.admin-page__secrets {
  white-space: pre-wrap;
  font-size: 0.85rem;
  margin: 0;
}
</style>
