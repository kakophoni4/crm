<script setup lang="ts">
import type { DataTableColumns, SelectOption } from 'naive-ui'
import {
  NButton,
  NDataTable,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NSwitch,
  useMessage,
} from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'

import type { Department, Group } from '@/features/admin/api'
import { listDepartments, listGroups } from '@/features/admin/api'
import {
  createTelephonyAccount,
  deactivateTelephonyAccount,
  listTelephonyAccounts,
  updateTelephonyAccount,
  type TelephonyAccount,
} from '@/features/telephony/api'
import { AppError } from '@/shared/api/http'

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const rows = ref<TelephonyAccount[]>([])
const departments = ref<Department[]>([])
const groups = ref<Group[]>([])
const showModal = ref(false)
const editing = ref<TelephonyAccount | null>(null)

const form = ref({
  name: '',
  department_id: null as number | null,
  group_id: null as number | null,
  sip_host: '',
  sip_port: 5060,
  sip_transport: 'udp' as 'udp' | 'tcp' | 'tls',
  sip_username: '',
  sip_password: '',
  outbound_caller_id: '',
  pbx_extension_prefix: '',
  webrtc_ws_url: '',
  is_active: true,
})

const departmentOptions = computed<SelectOption[]>(() =>
  departments.value.map((department) => ({ label: department.name, value: department.id })),
)

const groupOptions = computed<SelectOption[]>(() =>
  groups.value
    .filter((group) => group.department_id === form.value.department_id)
    .map((group) => ({ label: group.name, value: group.id })),
)

const columns = computed<DataTableColumns<TelephonyAccount>>(() => [
  { title: 'Name', key: 'name', minWidth: 160 },
  { title: 'Provider', key: 'provider', width: 100 },
  {
    title: 'Scope',
    key: 'scope',
    minWidth: 180,
    render: (row) => row.group_name ?? row.department_name ?? `Department #${row.department_id}`,
  },
  {
    title: 'SIP',
    key: 'sip',
    minWidth: 220,
    render: (row) => `${row.sip_username}@${row.sip_host}:${row.sip_port}`,
  },
  {
    title: 'Active',
    key: 'is_active',
    width: 90,
    render: (row) => (row.is_active ? 'yes' : 'no'),
  },
  {
    title: '',
    key: 'actions',
    width: 190,
    render: (row) =>
      h(NSpace, null, () => [
        h(NButton, { size: 'small', onClick: () => openEdit(row) }, { default: () => 'Edit' }),
        h(
          NButton,
          {
            size: 'small',
            type: 'warning',
            disabled: !row.is_active,
            onClick: () => onDeactivate(row),
          },
          { default: () => 'Disable' },
        ),
      ]),
  },
])

function resetForm(): void {
  form.value = {
    name: '',
    department_id: departments.value[0]?.id ?? null,
    group_id: null,
    sip_host: '',
    sip_port: 5060,
    sip_transport: 'udp',
    sip_username: '',
    sip_password: '',
    outbound_caller_id: '',
    pbx_extension_prefix: '',
    webrtc_ws_url: '',
    is_active: true,
  }
}

function openCreate(): void {
  editing.value = null
  resetForm()
  showModal.value = true
}

function openEdit(row: TelephonyAccount): void {
  editing.value = row
  form.value = {
    name: row.name,
    department_id: row.department_id,
    group_id: row.group_id,
    sip_host: row.sip_host,
    sip_port: row.sip_port,
    sip_transport: row.sip_transport,
    sip_username: row.sip_username,
    sip_password: '',
    outbound_caller_id: row.outbound_caller_id ?? '',
    pbx_extension_prefix: row.pbx_extension_prefix ?? '',
    webrtc_ws_url: row.webrtc_ws_url ?? '',
    is_active: row.is_active,
  }
  showModal.value = true
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [deptItems, groupItems, accountItems] = await Promise.all([
      listDepartments(),
      listGroups(),
      listTelephonyAccounts(),
    ])
    departments.value = deptItems
    groups.value = groupItems
    rows.value = accountItems
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Failed to load telephony')
  } finally {
    loading.value = false
  }
}

async function onSubmit(): Promise<void> {
  if (form.value.department_id == null) {
    message.warning('Select department')
    return
  }
  if (!editing.value && !form.value.sip_password) {
    message.warning('Enter SIP password')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.value.name,
      department_id: form.value.department_id,
      group_id: form.value.group_id,
      sip_host: form.value.sip_host,
      sip_port: form.value.sip_port,
      sip_transport: form.value.sip_transport,
      sip_username: form.value.sip_username,
      outbound_caller_id: form.value.outbound_caller_id || null,
      pbx_extension_prefix: form.value.pbx_extension_prefix || null,
      webrtc_ws_url: form.value.webrtc_ws_url || null,
      is_active: form.value.is_active,
      ...(form.value.sip_password ? { sip_password: form.value.sip_password } : {}),
    }
    const saved = editing.value
      ? await updateTelephonyAccount(editing.value.id, payload)
      : await createTelephonyAccount({
          ...payload,
          sip_password: form.value.sip_password,
        })
    rows.value = editing.value
      ? rows.value.map((row) => (row.id === saved.id ? saved : row))
      : [saved, ...rows.value]
    showModal.value = false
    message.success('Telephony account saved')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Failed to save telephony account')
  } finally {
    saving.value = false
  }
}

async function onDeactivate(row: TelephonyAccount): Promise<void> {
  try {
    const updated = await deactivateTelephonyAccount(row.id)
    rows.value = rows.value.map((item) => (item.id === updated.id ? updated : item))
    message.success('Telephony account disabled')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Failed to disable account')
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="settings-page">
    <header class="settings-page__header">
      <div>
        <h1 class="settings-page__title">Telephony accounts</h1>
        <p class="settings-page__hint">Bitcall SIP credentials for the PBX/WebRTC bridge.</p>
      </div>
      <NButton type="primary" @click="openCreate">Add Bitcall SIP</NButton>
    </header>

    <NSpin :show="loading">
      <NDataTable :columns="columns" :data="rows" :row-key="(row: TelephonyAccount) => row.id" />
    </NSpin>

    <NModal v-model:show="showModal" preset="card" :title="editing ? 'Edit SIP account' : 'Add Bitcall SIP'" class="telephony-modal">
      <NForm label-placement="top">
        <NFormItem label="Name">
          <NInput v-model:value="form.name" placeholder="Bitcall Main" />
        </NFormItem>
        <NFormItem label="Department">
          <NSelect v-model:value="form.department_id" :options="departmentOptions" />
        </NFormItem>
        <NFormItem label="Group">
          <NSelect v-model:value="form.group_id" :options="groupOptions" clearable />
        </NFormItem>
        <div class="telephony-modal__grid">
          <NFormItem label="SIP host">
            <NInput v-model:value="form.sip_host" placeholder="sip.bitcall.example" />
          </NFormItem>
          <NFormItem label="Port">
            <NInputNumber v-model:value="form.sip_port" :min="1" :max="65535" />
          </NFormItem>
        </div>
        <div class="telephony-modal__grid">
          <NFormItem label="Transport">
            <NSelect
              v-model:value="form.sip_transport"
              :options="[
                { label: 'UDP', value: 'udp' },
                { label: 'TCP', value: 'tcp' },
                { label: 'TLS', value: 'tls' },
              ]"
            />
          </NFormItem>
          <NFormItem label="SIP username">
            <NInput v-model:value="form.sip_username" />
          </NFormItem>
        </div>
        <NFormItem :label="editing ? 'SIP password (leave blank to keep)' : 'SIP password'">
          <NInput v-model:value="form.sip_password" type="password" show-password-on="click" />
        </NFormItem>
        <div class="telephony-modal__grid">
          <NFormItem label="Outbound caller ID">
            <NInput v-model:value="form.outbound_caller_id" placeholder="+79005550123" />
          </NFormItem>
          <NFormItem label="Extension prefix">
            <NInput v-model:value="form.pbx_extension_prefix" placeholder="7" />
          </NFormItem>
        </div>
        <NFormItem label="WebRTC WebSocket URL">
          <NInput v-model:value="form.webrtc_ws_url" placeholder="wss://pbx.example.test/ws" />
        </NFormItem>
        <NFormItem label="Active">
          <NSwitch v-model:value="form.is_active" />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showModal = false">Cancel</NButton>
          <NButton type="primary" :loading="saving" @click="onSubmit">Save</NButton>
        </NSpace>
      </template>
    </NModal>
  </section>
</template>

<style scoped>
.settings-page__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.settings-page__title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}

.settings-page__hint {
  margin: 6px 0 0;
  color: var(--app-text-muted);
}

.telephony-modal {
  max-width: 720px;
}

.telephony-modal__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}

@media (max-width: 720px) {
  .settings-page__header,
  .telephony-modal__grid {
    grid-template-columns: 1fr;
  }

  .settings-page__header {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
