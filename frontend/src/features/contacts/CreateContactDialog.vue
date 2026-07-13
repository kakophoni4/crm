<script setup lang="ts">
import { NButton, NForm, NFormItem, NInput, NModal, NSelect, useMessage } from 'naive-ui'
import type { SelectOption } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import type { Contact } from '@/entities/contact/types'
import { listGroups } from '@/features/admin/api'
import { createContact } from '@/features/contacts/api'
import { AppError } from '@/shared/api/http'
import { normalizeRussianPhone } from '@/shared/lib/phone'
import { useAuthStore } from '@/shared/store/auth'

const props = withDefaults(
  defineProps<{
    show: boolean
    initialPhone?: string
    departmentId?: number | null
    source?: string
    requirePhone?: boolean
    openWorkspace?: boolean
  }>(),
  {
    initialPhone: '',
    departmentId: null,
    source: 'manual',
    requirePhone: false,
    openWorkspace: true,
  },
)

const emit = defineEmits<{
  'update:show': [value: boolean]
  created: [contact: Contact]
}>()

const message = useMessage()
const auth = useAuthStore()
const creating = ref(false)
const groupsLoading = ref(false)
const workspaceGroupId = ref<number | null>(null)
const groupOptions = ref<SelectOption[]>([])
const form = ref({
  full_name: '',
  phone: '',
  email: '',
  telegram_username: '',
})

const showGroupSelect = computed(
  () => props.openWorkspace && (groupOptions.value.length > 1 || auth.canForceCardOwner),
)

function defaultWorkspaceGroupId(): number | null {
  const user = auth.user
  if (!user) return null
  if (user.group_ids.length === 1) return user.group_ids[0]
  if (user.group_id != null) return user.group_id
  return null
}

async function loadWorkspaceGroups(): Promise<void> {
  if (!props.openWorkspace) {
    groupOptions.value = []
    return
  }
  groupsLoading.value = true
  try {
    const departmentId = props.departmentId ?? auth.user?.department_id ?? undefined
    const groups = await listGroups(departmentId)
    groupOptions.value = groups.map((group) => ({
      label: group.name,
      value: group.id,
    }))
    if (workspaceGroupId.value == null && groupOptions.value.length === 1) {
      workspaceGroupId.value = Number(groupOptions.value[0]?.value)
    }
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить группы')
  } finally {
    groupsLoading.value = false
  }
}

function resetForm(phone = ''): void {
  form.value = {
    full_name: '',
    phone,
    email: '',
    telegram_username: '',
  }
  workspaceGroupId.value = defaultWorkspaceGroupId()
}

watch(
  () => props.show,
  (visible) => {
    if (!visible) return
    resetForm(props.initialPhone?.trim() ?? '')
    void loadWorkspaceGroups()
  },
)

function close(): void {
  emit('update:show', false)
}

async function submit(): Promise<void> {
  const name = form.value.full_name.trim()
  if (!name) {
    message.warning('Введите имя клиента')
    return
  }

  const rawPhone = form.value.phone.trim()
  let phone: string | null = null
  if (rawPhone) {
    phone = normalizeRussianPhone(rawPhone)
    if (!phone) {
      message.warning('Введите номер в формате +7XXXXXXXXXX')
      return
    }
  } else if (props.requirePhone) {
    message.warning('Введите номер в формате +7XXXXXXXXXX')
    return
  }

  if (props.openWorkspace && workspaceGroupId.value == null) {
    message.warning('Выберите группу для диалога')
    return
  }

  creating.value = true
  try {
    const telegram = form.value.telegram_username.trim().replace(/^@/, '')
    const contact = await createContact({
      full_name: name,
      phone,
      email: form.value.email.trim() || null,
      telegram_username: telegram || null,
      assigned_department_id: props.departmentId,
      source: props.source,
      open_workspace: props.openWorkspace,
      workspace_group_id: workspaceGroupId.value,
      custom_fields: props.source === 'telephony' ? { source: 'telephony' } : undefined,
    })
    message.success('Контакт создан')
    emit('created', contact)
    close()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось создать контакт')
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    class="create-contact-dialog"
    style="width: min(440px, calc(100vw - 24px))"
    title="Создать контакт"
    :bordered="false"
    @update:show="emit('update:show', $event)"
  >
    <NForm size="small" @submit.prevent="submit">
      <NFormItem v-if="showGroupSelect" label="Группа" required>
        <NSelect
          v-model:value="workspaceGroupId"
          :options="groupOptions"
          :loading="groupsLoading"
          placeholder="Выберите группу"
          clearable
        />
      </NFormItem>
      <NFormItem label="Имя" required>
        <NInput
          v-model:value="form.full_name"
          placeholder="Имя клиента"
          autofocus
          @keydown.enter.prevent="submit"
        />
      </NFormItem>
      <NFormItem label="Телефон" :required="requirePhone">
        <NInput v-model:value="form.phone" placeholder="+7XXXXXXXXXX" />
      </NFormItem>
      <NFormItem label="Email">
        <NInput v-model:value="form.email" placeholder="Необязательно" />
      </NFormItem>
      <NFormItem label="Telegram">
        <NInput v-model:value="form.telegram_username" placeholder="@username, если клиент дал" />
      </NFormItem>
      <div class="create-contact-dialog__actions">
        <NButton :disabled="creating" @click="close">Отмена</NButton>
        <NButton type="primary" :loading="creating" @click="submit">Создать</NButton>
      </div>
    </NForm>
  </NModal>
</template>

<style scoped>
.create-contact-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
</style>
