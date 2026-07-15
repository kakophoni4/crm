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
import { computed, h, onMounted, ref, watch } from 'vue'

import type { BotItem, Department, Group, AdminUser } from '@/features/admin/api'
import {
  createBot,
  listBots,
  listDepartments,
  listGroups,
  listUsers,
  rotateBotSecret,
  setBotGroupAssignments,
  updateBot,
} from '@/features/admin/api'
import TelephonyAccountsPanel from '@/features/telephony/TelephonyAccountsPanel.vue'
import { FIXED_SERVICE_TYPES } from '@/features/leads/service-types'
import { AppError } from '@/shared/api/http'

const message = useMessage()
const loading = ref(false)
const rows = ref<BotItem[]>([])
const departments = ref<Department[]>([])
const groups = ref<Group[]>([])
const users = ref<AdminUser[]>([])
const showModal = ref(false)
const showEditModal = ref(false)
const secretsModal = ref(false)
const lastSecrets = ref('')
const editingBot = ref<BotItem | null>(null)
const form = ref({
  channel: 'telegram' as 'telegram' | 'whatsapp',
  code: '',
  name: '',
  department_id: null as number | null,
  outbound_url: 'https://example.com/outbound',
  inbound_secret: '',
  outbound_secret: '',
  green_api_url: '',
  green_media_url: '',
  green_instance_id: '',
  green_api_token: '',
  service_types: ['Деревья', 'ОПТ'] as string[],
  default_owner_user_id: null as number | null,
})
const editForm = ref({
  name: '',
  department_id: null as number | null,
  is_active: true,
  green_api_url: '',
  green_media_url: '',
  green_instance_id: '',
  green_api_token: '',
  service_types: ['Деревья', 'ОПТ'] as string[],
  assigned_group_ids: [] as number[],
  default_owner_user_id: null as number | null,
})

const isWhatsAppForm = computed(() => form.value.channel === 'whatsapp')
const isWhatsAppEdit = computed(() => editingBot.value?.channel === 'whatsapp')

const serviceTypeOptions = computed<SelectOption[]>(() =>
  FIXED_SERVICE_TYPES.map((row) => ({ label: row.label, value: row.value })),
)

function formatServiceTypes(types: string[] | undefined): string {
  if (!types?.length) return 'Деревья, ОПТ'
  return types.join(', ')
}

function randomSecret(): string {
  const bytes = new Uint8Array(24)
  crypto.getRandomValues(bytes)
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').slice(0, 32)
}

function onGreenInstanceIdInput(value: string): void {
  form.value.green_instance_id = value
  const id = value.trim()
  if (!id || form.value.green_api_url.trim() || form.value.green_media_url.trim()) return
  const shard = id.slice(0, 4)
  if (/^\d{4}$/.test(shard)) {
    form.value.green_api_url = `https://${shard}.api.green-api.com`
    form.value.green_media_url = `https://${shard}.api.green-api.com`
  }
}

const departmentOptions = computed<SelectOption[]>(() =>
  departments.value.map((d) => ({ label: d.name, value: d.id })),
)

function groupOptionsForDepartment(departmentId: number | null): SelectOption[] {
  if (departmentId == null) return []
  return groups.value
    .filter((g) => g.department_id === departmentId)
    .map((g) => ({ label: g.name, value: g.id }))
}

function formatGroupNames(row: BotItem): string {
  if (row.assigned_group_names?.length) return row.assigned_group_names.join(', ')
  return '—'
}

const editGroupOptions = computed(() => groupOptionsForDepartment(editForm.value.department_id))

const userOptions = computed<SelectOption[]>(() =>
  users.value
    .filter((u) => u.status === 'active' && u.role !== 'accountant')
    .map((u) => ({
      label: `${u.full_name} (@${u.username})`,
      value: u.id,
    })),
)

const columns = computed<DataTableColumns<BotItem>>(() => [
  { title: 'Код', key: 'code', width: 140, ellipsis: { tooltip: true } },
  {
    title: 'Канал',
    key: 'channel',
    width: 100,
    render: (row) => (row.channel === 'whatsapp' ? 'WhatsApp' : 'Telegram'),
  },
  { title: 'Название', key: 'name', minWidth: 160, ellipsis: { tooltip: true } },
  {
    title: 'Отдел',
    key: 'department_name',
    width: 140,
    ellipsis: { tooltip: true },
    render: (row) => row.department_name ?? `#${row.department_id}`,
  },
  {
    title: 'Услуги',
    key: 'service_types',
    width: 130,
    ellipsis: { tooltip: true },
    render: (row) => formatServiceTypes(row.service_types),
  },
  {
    title: 'Группы',
    key: 'assigned_group_ids',
    minWidth: 180,
    ellipsis: { tooltip: true },
    render: (row) => formatGroupNames(row),
  },
  {
    title: 'Активен',
    key: 'is_active',
    width: 80,
    render: (row) => (row.is_active ? 'да' : 'нет'),
  },
  {
    title: '',
    key: 'actions',
    width: 220,
    fixed: 'right',
    render: (row) =>
      h(NSpace, { size: 'small', wrap: true }, () => [
        h(
          NButton,
          { size: 'small', onClick: () => openEdit(row) },
          { default: () => 'Изменить' },
        ),
        h(
          NButton,
          { size: 'small', onClick: () => onRotate(row, 'inbound') },
          { default: () => 'Входящий ключ' },
        ),
        h(
          NButton,
          { size: 'small', onClick: () => onRotate(row, 'outbound') },
          { default: () => 'Исходящий ключ' },
        ),
      ]),
  },
])

function openCreate(): void {
  form.value = {
    channel: 'telegram',
    code: '',
    name: '',
    department_id: departments.value[0]?.id ?? null,
    outbound_url: 'https://example.com/outbound',
    inbound_secret: randomSecret(),
    outbound_secret: randomSecret(),
    green_api_url: '',
    green_media_url: '',
    green_instance_id: '',
    green_api_token: '',
    service_types: ['Деревья', 'ОПТ'],
    default_owner_user_id: null,
  }
  showModal.value = true
}

function openCreateWhatsApp(): void {
  openCreate()
  form.value.channel = 'whatsapp'
}

function openEdit(row: BotItem): void {
  editingBot.value = row
  editForm.value = {
    name: row.name,
    department_id: row.department_id,
    is_active: row.is_active,
    green_api_url: row.green_api_url ?? '',
    green_media_url: row.green_media_url ?? '',
    green_instance_id: row.green_instance_id ?? '',
    green_api_token: '',
    service_types: row.service_types?.length ? [...row.service_types] : ['Деревья', 'ОПТ'],
    assigned_group_ids: [...row.assigned_group_ids],
    default_owner_user_id: row.default_owner_user_id ?? null,
  }
  showEditModal.value = true
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [deptItems, groupItems, botItems, userItems] = await Promise.all([
      listDepartments(),
      listGroups(),
      listBots(),
      listUsers(),
    ])
    departments.value = deptItems
    groups.value = groupItems
    rows.value = botItems
    users.value = userItems
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
  if (!form.value.service_types.length) {
    message.warning('Выберите хотя бы одну услугу')
    return
  }
  if (form.value.channel === 'telegram') {
    if (form.value.inbound_secret.length < 16 || form.value.outbound_secret.length < 16) {
      message.warning('Секреты должны быть не короче 16 символов')
      return
    }
  } else if (!form.value.green_instance_id.trim() || !form.value.green_api_token.trim()) {
    message.warning('Укажите GREEN API idInstance и apiTokenInstance')
    return
  }
  try {
    const body: Parameters<typeof createBot>[0] = {
      code: form.value.code.trim(),
      name: form.value.name.trim(),
      channel: form.value.channel,
      department_id: form.value.department_id,
    }
    if (form.value.channel === 'telegram') {
      body.outbound_url = form.value.outbound_url.trim()
      body.inbound_secret = form.value.inbound_secret
      body.outbound_secret = form.value.outbound_secret
    } else {
      body.green_instance_id = form.value.green_instance_id.trim()
      body.green_api_token = form.value.green_api_token.trim()
      if (form.value.green_api_url.trim()) body.green_api_url = form.value.green_api_url.trim()
      if (form.value.green_media_url.trim()) body.green_media_url = form.value.green_media_url.trim()
    }
    if (form.value.service_types.length) {
      body.service_types = [...form.value.service_types]
    }
    if (form.value.default_owner_user_id != null) {
      body.default_owner_user_id = form.value.default_owner_user_id
    }
    const created = await createBot(body)
    showModal.value = false
    if (created.secrets) {
      lastSecrets.value = `inbound: ${created.secrets.inbound_secret}\noutbound: ${created.secrets.outbound_secret}\n\n${created.secrets.warning}`
      secretsModal.value = true
    }
    message.success(form.value.channel === 'whatsapp' ? 'WhatsApp бот создан и webhook настроен' : 'Бот создан')
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
  if (!editForm.value.service_types.length) {
    message.warning('Выберите хотя бы одну услугу')
    return
  }
  try {
    const payload: Parameters<typeof updateBot>[1] = {
      name: editForm.value.name.trim(),
      is_active: editForm.value.is_active,
      service_types: [...editForm.value.service_types],
    }
    if (editForm.value.department_id != null && editForm.value.department_id !== bot.department_id) {
      payload.department_id = editForm.value.department_id
    }
    if (bot.channel === 'whatsapp') {
      payload.green_instance_id = editForm.value.green_instance_id.trim() || null
      payload.green_api_url = editForm.value.green_api_url.trim() || null
      payload.green_media_url = editForm.value.green_media_url.trim() || null
      if (editForm.value.green_api_token.trim()) {
        payload.green_api_token = editForm.value.green_api_token.trim()
      }
    }
    if (editForm.value.default_owner_user_id != null) {
      payload.default_owner_user_id = editForm.value.default_owner_user_id
    } else if (bot.default_owner_user_id != null) {
      payload.clear_default_owner = true
    }
    await updateBot(bot.id, payload)
    const groupsChanged =
      editForm.value.assigned_group_ids.length !== bot.assigned_group_ids.length ||
      editForm.value.assigned_group_ids.some((id) => !bot.assigned_group_ids.includes(id))
    if (groupsChanged) {
      await setBotGroupAssignments(bot.id, editForm.value.assigned_group_ids)
    }
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

watch(
  () => editForm.value.department_id,
  (departmentId) => {
    if (!showEditModal.value) return
    const validIds = new Set(groupOptionsForDepartment(departmentId).map((row) => row.value as number))
    editForm.value.assigned_group_ids = editForm.value.assigned_group_ids.filter((id) =>
      validIds.has(id),
    )
  },
)
</script>

<template>
  <section class="admin-page">
    <header class="admin-page__header">
      <div>
        <h1 class="admin-page__title">Боты</h1>
        <p class="admin-page__hint">
          Привяжите бота к отделу и назначьте одну группу — тогда чаты и передача карточек идут
          в рамках этой группы. Без группы чаты попадают в общий ящик отдела, передача недоступна.
        </p>
      </div>
      <NButton type="primary" @click="openCreate">Создать бота</NButton>
      <NButton @click="openCreateWhatsApp">+ WhatsApp</NButton>
    </header>
    <NSpin :show="loading">
      <NDataTable
        :columns="columns"
        :data="rows"
        :row-key="(r: BotItem) => r.id"
        :scroll-x="1100"
      />
    </NSpin>

    <TelephonyAccountsPanel />

    <NModal
      v-model:show="showModal"
      preset="card"
      :title="isWhatsAppForm ? 'Новый WhatsApp бот' : 'Новый бот'"
      style="max-width: 520px"
    >
      <NForm label-placement="top">
        <NFormItem v-if="!isWhatsAppForm" label="Канал">
          <NSelect
            v-model:value="form.channel"
            :options="[
              { label: 'Telegram', value: 'telegram' },
              { label: 'WhatsApp (GREEN API)', value: 'whatsapp' },
            ]"
          />
        </NFormItem>
        <NFormItem label="Код">
          <NInput v-model:value="form.code" placeholder="whatsapp_support_1" />
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
        <NFormItem label="Услуги в сделках">
          <NSelect
            v-model:value="form.service_types"
            multiple
            :options="serviceTypeOptions"
            placeholder="Деревья и ОПТ"
          />
        </NFormItem>
        <NFormItem
          label="Фиксированный владелец карточек"
          extra="Все новые лиды с этого бота назначаются только этому менеджеру (например ИнфоСлед → Дейнерис)."
        >
          <NSelect
            v-model:value="form.default_owner_user_id"
            clearable
            filterable
            :options="userOptions"
            placeholder="По умолчанию — round-robin в группе"
          />
        </NFormItem>
        <template v-if="isWhatsAppForm">
          <p class="admin-page__wa-hint">
            Вставьте данные из консоли GREEN API. Секреты ХУИтРИКС и webhook настроятся автоматически.
          </p>
          <NFormItem label="idInstance">
            <NInput
              :value="form.green_instance_id"
              placeholder="1105653814"
              @update:value="onGreenInstanceIdInput"
            />
          </NFormItem>
          <NFormItem label="apiTokenInstance">
            <NInput
              v-model:value="form.green_api_token"
              type="password"
              show-password-on="click"
            />
          </NFormItem>
          <NFormItem label="apiUrl (необязательно)">
            <NInput v-model:value="form.green_api_url" placeholder="https://1105.api.green-api.com" />
          </NFormItem>
          <NFormItem label="mediaUrl (необязательно)">
            <NInput v-model:value="form.green_media_url" placeholder="https://1105.api.green-api.com" />
          </NFormItem>
        </template>
        <template v-else>
          <NFormItem label="URL исходящих событий">
            <NInput v-model:value="form.outbound_url" />
          </NFormItem>
          <NFormItem label="Входящий секрет (inbound)">
            <NInput v-model:value="form.inbound_secret" type="password" show-password-on="click" />
          </NFormItem>
          <NFormItem label="Исходящий секрет (outbound)">
            <NInput v-model:value="form.outbound_secret" type="password" show-password-on="click" />
          </NFormItem>
        </template>
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
        <NFormItem label="Услуги в сделках">
          <NSelect
            v-model:value="editForm.service_types"
            multiple
            :options="serviceTypeOptions"
            placeholder="Деревья и ОПТ"
          />
        </NFormItem>
        <NFormItem
          label="Фиксированный владелец карточек"
          extra="Новые и авто-назначенные карточки бота уходят только этому менеджеру. Ручные передачи не трогаем."
        >
          <NSelect
            v-model:value="editForm.default_owner_user_id"
            clearable
            filterable
            :options="userOptions"
            placeholder="По умолчанию — round-robin в группе"
          />
        </NFormItem>
        <NFormItem label="Группы">
          <NSelect
            v-model:value="editForm.assigned_group_ids"
            multiple
            filterable
            :options="editGroupOptions"
            placeholder="Не распределён (ящик отдела)"
          />
        </NFormItem>
        <template v-if="isWhatsAppEdit">
          <p v-if="editingBot?.whatsapp_webhook_url" class="admin-page__wa-hint">
            Webhook: {{ editingBot.whatsapp_webhook_url }}
          </p>
          <NFormItem label="idInstance">
            <NInput v-model:value="editForm.green_instance_id" />
          </NFormItem>
          <NFormItem label="apiTokenInstance">
            <NInput
              v-model:value="editForm.green_api_token"
              type="password"
              show-password-on="click"
              :placeholder="editingBot?.has_green_api_token ? '•••••••• (оставьте пустым, чтобы не менять)' : ''"
            />
          </NFormItem>
          <NFormItem label="apiUrl">
            <NInput v-model:value="editForm.green_api_url" />
          </NFormItem>
          <NFormItem label="mediaUrl">
            <NInput v-model:value="editForm.green_media_url" />
          </NFormItem>
        </template>
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

.admin-page__wa-hint {
  margin: 0 0 12px;
  font-size: 0.85rem;
  color: var(--app-text-muted);
  line-height: 1.4;
}
</style>
