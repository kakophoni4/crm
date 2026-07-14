<script setup lang="ts">
import { NButton, NCard, NForm, NFormItem, NInput, NSpace, NSpin, NSwitch, useMessage } from 'naive-ui'
import { onMounted, ref } from 'vue'

import { getNotificationBot, patchNotificationBot } from '@/features/notifications/api'
import { AppError } from '@/shared/api/http'

const message = useMessage()
const loading = ref(true)
const saving = ref(false)
const enabled = ref(false)
const username = ref<string | null>(null)
const hasToken = ref(false)
const tokenInput = ref('')

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await getNotificationBot()
    enabled.value = data.is_enabled
    username.value = data.bot_username
    hasToken.value = data.has_token
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить')
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  saving.value = true
  try {
    const body: { bot_token?: string; is_enabled?: boolean } = {
      is_enabled: enabled.value,
    }
    if (tokenInput.value.trim()) {
      body.bot_token = tokenInput.value.trim()
    }
    const data = await patchNotificationBot(body)
    enabled.value = data.is_enabled
    username.value = data.bot_username
    hasToken.value = data.has_token
    tokenInput.value = ''
    message.success('Сохранено')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void load()
})
</script>

<template>
  <section class="admin-notif-bot">
    <header class="admin-notif-bot__header">
      <h1>Бот уведомлений</h1>
    </header>

    <NSpin :show="loading">
      <NCard size="small" style="max-width: 560px">
        <NForm label-placement="top">
          <NFormItem label="Включён">
            <NSwitch v-model:value="enabled" />
          </NFormItem>
          <NFormItem label="Токен бота">
            <NInput
              v-model:value="tokenInput"
              type="password"
              show-password-on="click"
              :placeholder="hasToken ? '•••••••• (оставьте пустым, чтобы не менять)' : '123456:AA...'"
            />
          </NFormItem>
          <NFormItem v-if="username" label="Username бота">
            <a :href="`https://t.me/${username}`" target="_blank" rel="noopener">@{{ username }}</a>
          </NFormItem>
          <NSpace>
            <NButton type="primary" :loading="saving" @click="save">Сохранить</NButton>
          </NSpace>
        </NForm>
      </NCard>
    </NSpin>
  </section>
</template>

<style scoped>
.admin-notif-bot__header {
  margin-bottom: 16px;
}
.admin-notif-bot__header h1 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}
</style>
