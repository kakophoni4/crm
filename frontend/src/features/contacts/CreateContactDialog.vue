<script setup lang="ts">
import { NButton, NForm, NFormItem, NInput, NModal, useMessage } from 'naive-ui'
import { ref, watch } from 'vue'

import type { Contact } from '@/entities/contact/types'
import { createContact } from '@/features/contacts/api'
import { AppError } from '@/shared/api/http'
import { normalizeRussianPhone } from '@/shared/lib/phone'

const props = withDefaults(
  defineProps<{
    show: boolean
    initialPhone?: string
    departmentId?: number | null
    source?: string
    requirePhone?: boolean
  }>(),
  {
    initialPhone: '',
    departmentId: null,
    source: 'manual',
    requirePhone: false,
  },
)

const emit = defineEmits<{
  'update:show': [value: boolean]
  created: [contact: Contact]
}>()

const message = useMessage()
const creating = ref(false)
const form = ref({
  full_name: '',
  phone: '',
  email: '',
  telegram_username: '',
})

function resetForm(phone = ''): void {
  form.value = {
    full_name: '',
    phone,
    email: '',
    telegram_username: '',
  }
}

watch(
  () => props.show,
  (visible) => {
    if (!visible) return
    resetForm(props.initialPhone?.trim() ?? '')
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
