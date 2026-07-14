<script setup lang="ts">
import { NButton, NCard, NForm, NFormItem, NInput, NSpace, NSpin, NSwitch, useMessage } from 'naive-ui'
import { onMounted, ref } from 'vue'

import {
  getNotificationBot,
  patchNotificationBot,
  syncNotificationBotWebhook,
} from '@/features/notifications/api'
import { AppError } from '@/shared/api/http'

const message = useMessage()
const loading = ref(true)
const saving = ref(false)
const syncing = ref(false)
const enabled = ref(false)
const username = ref<string | null>(null)
const hasToken = ref(false)
const webhookHint = ref('')
const tokenInput = ref('')

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await getNotificationBot()
    enabled.value = data.is_enabled
    username.value = data.bot_username
    hasToken.value = data.has_token
    webhookHint.value = data.webhook_hint
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
    webhookHint.value = data.webhook_hint
    tokenInput.value = ''
    message.success('Сохранено')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить')
  } finally {
    saving.value = false
  }
}

async function syncWebhook(): Promise<void> {
  syncing.value = true
  try {
    const data = await syncNotificationBotWebhook()
    webhookHint.value = data.webhook_hint
    message.success('Webhook перерегистрирован')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось обновить webhook')
  } finally {
    syncing.value = false
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
          <NFormItem v-if="webhookHint" label="Webhook">
            <code class="admin-notif-bot__wh">{{ webhookHint }}</code>
          </NFormItem>
          <NSpace>
            <NButton type="primary" :loading="saving" @click="save">Сохранить</NButton>
            <NButton
              v-if="hasToken && enabled"
              :loading="syncing"
              secondary
              @click="syncWebhook"
            >
              Перерегистрировать webhook
            </NButton>
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
.admin-notif-bot__wh {
  font-size: 0.85rem;
  word-break: break-all;
}
</style>
