<script setup lang="ts">
import {
  NButton,
  NCard,
  NDynamicTags,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NSpace,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  getNotificationSettings,
  linkTelegram,
  patchNotificationSettings,
  unlinkTelegram,
  type NotificationSettings,
} from '@/features/notifications/api'
import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'

const message = useMessage()
const router = useRouter()
const auth = useAuthStore()

const loading = ref(true)
const saving = ref(false)
const linking = ref(false)
const settings = ref<NotificationSettings | null>(null)
const telegramIdInput = ref('')
const timeoutMinutes = ref(15)
const mutePhrases = ref<string[]>([])

const isGroupSenior = computed(
  () => auth.user?.role === 'group_senior' || auth.user?.role === 'admin',
)
const botDeepLink = computed(() => {
  const u = settings.value?.bot_username
  return u ? `https://t.me/${u}` : null
})

async function load(): Promise<void> {
  loading.value = true
  try {
    settings.value = await getNotificationSettings()
    timeoutMinutes.value = settings.value.group_senior_timeout_minutes
    mutePhrases.value = [...settings.value.mute_phrases]
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить')
  } finally {
    loading.value = false
  }
}

async function onLink(): Promise<void> {
  const id = Number(telegramIdInput.value.trim())
  if (!Number.isFinite(id) || id <= 0) {
    message.warning('Введите числовой Telegram ID из бота')
    return
  }
  linking.value = true
  try {
    await linkTelegram(id)
    telegramIdInput.value = ''
    message.success('Telegram привязан')
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось привязать')
  } finally {
    linking.value = false
  }
}

async function onUnlink(linkId: number): Promise<void> {
  try {
    await unlinkTelegram(linkId)
    message.success('Привязка удалена')
    await load()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось отвязать')
  }
}

async function onSave(): Promise<void> {
  saving.value = true
  try {
    const body: { group_senior_timeout_minutes?: number; mute_phrases?: string[] } = {}
    if (isGroupSenior.value) {
      body.group_senior_timeout_minutes = timeoutMinutes.value
      body.mute_phrases = mutePhrases.value
    }
    settings.value = await patchNotificationSettings(body)
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
  <section class="notif-page">
    <header class="notif-page__header">
      <h1>Уведомления</h1>
      <p class="notif-page__sub">
        Привяжите Telegram, чтобы получать сообщения о чатах и новых карточках.
      </p>
    </header>

    <NSpin :show="loading">
      <NCard title="Привязать Telegram" size="small" class="notif-page__card">
        <p class="notif-page__hint">
          1. Откройте бота уведомлений
          <template v-if="botDeepLink">
            —
            <a :href="botDeepLink" target="_blank" rel="noopener">{{ botDeepLink }}</a>
          </template>
          <template v-else-if="!settings?.bot_enabled">
            (админ ещё не настроил токен бота)
          </template>
          .
          <br />
          2. Нажмите <b>Start</b> — бот пришлёт ваш ID.
          <br />
          3. Вставьте ID ниже и нажмите «Привязать».
        </p>

        <div v-if="settings?.telegram_links?.length" class="notif-page__links">
          <div v-for="link in settings.telegram_links" :key="link.id" class="notif-page__link-row">
            <NTag type="success" size="small">ID {{ link.telegram_user_id }}</NTag>
            <span v-if="link.telegram_username" class="notif-page__muted">@{{ link.telegram_username }}</span>
            <NButton size="tiny" quaternary type="error" @click="onUnlink(link.id)">Отвязать</NButton>
          </div>
        </div>

        <NSpace v-if="settings?.can_link_multiple || !settings?.telegram_links?.length" align="center">
          <NInput
            v-model:value="telegramIdInput"
            placeholder="Telegram ID"
            style="max-width: 220px"
          />
          <NButton type="primary" :loading="linking" @click="onLink">Привязать</NButton>
        </NSpace>
        <p v-else class="notif-page__muted">
          У вашей роли можно привязать только один Telegram ID. Отвяжите текущий, чтобы заменить.
        </p>
      </NCard>

      <NCard
        v-if="isGroupSenior"
        title="Настройки старшего группы"
        size="small"
        class="notif-page__card"
      >
        <NForm label-placement="top">
          <NFormItem
            label="Уведомлять, если нет ответа, мин"
            extra="Если оператор не ответил за это время — вам придёт эскалация по всем чатам группы."
          >
            <NInputNumber v-model:value="timeoutMinutes" :min="1" :max="1440" style="width: 100%" />
          </NFormItem>
          <NFormItem
            label="Не уведомлять по фразам"
            extra="Если входящее содержит одну из фраз (например «спасибо», «доброй ночи») — эскалация вам не уйдёт."
          >
            <NDynamicTags v-model:value="mutePhrases" />
          </NFormItem>
          <NButton type="primary" :loading="saving" @click="onSave">Сохранить</NButton>
        </NForm>
      </NCard>

      <NCard v-if="settings?.can_view_history" title="История" size="small" class="notif-page__card">
        <p class="notif-page__hint">Кому ушло уведомление и кто нажал «Прочитано».</p>
        <NButton @click="router.push({ name: 'notification-history' })">Открыть историю</NButton>
      </NCard>
    </NSpin>
  </section>
</template>

<style scoped>
.notif-page__header {
  margin-bottom: 16px;
}
.notif-page__header h1 {
  margin: 0 0 4px;
  font-size: 1.5rem;
  font-weight: 700;
}
.notif-page__sub,
.notif-page__hint,
.notif-page__muted {
  color: var(--app-text-muted);
}
.notif-page__hint {
  margin: 0 0 12px;
  line-height: 1.5;
}
.notif-page__card {
  margin-bottom: 16px;
  max-width: 640px;
}
.notif-page__links {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}
.notif-page__link-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
</style>
