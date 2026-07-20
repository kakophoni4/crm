<script setup lang="ts">
import {
  NButton,
  NCard,
  NDynamicTags,
  NInput,
  NInputNumber,
  NSelect,
  NSpace,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  useMessage,
} from 'naive-ui'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useChatNotificationsStore } from '@/features/chats/notifications-store'
import {
  getEscalationPolicy,
  getNotificationBot,
  getNotificationHistory,
  getNotificationSettings,
  linkTelegram,
  patchEscalationPolicy,
  patchMutePhrases,
  patchNotificationBot,
  type EscalationPolicy,
  type NotificationSettings,
  type StaffNotificationEvent,
  unlinkTelegram,
} from '@/features/notifications/api'
import {
  peekNotificationHistoryCache,
  peekNotificationSettingsCache,
  setNotificationHistoryCache,
  setNotificationSettingsCache,
} from '@/features/notifications/cache'
import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'

const KIND_LABEL: Record<string, string> = {
  inbound_message: 'Сообщение',
  new_card: 'Новая карточка',
  escalation_group_senior: 'Эскалация → старший группы',
  escalation_dept_senior: 'Эскалация → старший отдела',
  escalation_admin: 'Эскалация → админ',
}

const STATUS_TYPE: Record<string, 'success' | 'warning' | 'error' | 'default' | 'info'> = {
  sent: 'warning',
  acked: 'success',
  failed: 'error',
}

const STATUS_LABEL: Record<string, string> = {
  sent: 'Не ознакомлен',
  acked: 'Прочитано',
  failed: 'Ошибка',
}

const message = useMessage()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const chatNotifications = useChatNotificationsStore()

function tabFromRoute(): 'history' | 'settings' {
  return String(route.query.tab || '') === 'settings' ? 'settings' : 'history'
}

const loading = ref(false)
const savingEscalation = ref(false)
const savingMute = ref(false)
const savingToken = ref(false)
const linking = ref(false)
const settings = ref<NotificationSettings | null>(null)
const escalationPolicy = ref<EscalationPolicy | null>(null)
const telegramIdInput = ref('')
const timeoutMinutes = ref(15)
const mutePhrases = ref<string[]>([])
const tokenInput = ref('')
const hasToken = ref(true)

/** Default history — avoid settings flash while settings API loads. */
const activeTab = ref<'history' | 'settings'>(tabFromRoute())

const historyLoading = ref(false)
const historyItems = ref<StaffNotificationEvent[]>([])
const statusFilter = ref('')

const userId = computed(() => auth.user?.id ?? null)

function hydrateFromCache(): void {
  const cachedSettings = peekNotificationSettingsCache(userId.value)
  if (cachedSettings) {
    settings.value = cachedSettings.settings
    mutePhrases.value = [...(cachedSettings.settings.mute_phrases || [])]
    chatNotifications.setMutePhrases(mutePhrases.value)
    escalationPolicy.value = cachedSettings.escalation
    timeoutMinutes.value = cachedSettings.escalation?.timeout_minutes ?? 15
    hasToken.value = cachedSettings.hasToken
    if (!cachedSettings.settings.can_view_history) {
      activeTab.value = 'settings'
    } else if (!route.query.tab) {
      activeTab.value = 'history'
    }
  }
  const cachedHistory = peekNotificationHistoryCache(userId.value, statusFilter.value)
  if (cachedHistory) {
    historyItems.value = cachedHistory.items
  }
}

const statusOptions = [
  { label: 'Все', value: '' },
  { label: 'Не ознакомлен', value: 'sent' },
  { label: 'Прочитано', value: 'acked' },
  { label: 'Ошибка', value: 'failed' },
]

const canManageEscalation = computed(() => Boolean(settings.value?.can_manage_escalation))
const canManageBot = computed(() => Boolean(settings.value?.can_manage_bot))
const canViewHistory = computed(() => Boolean(settings.value?.can_view_history))
const canLinkTelegram = computed(
  () => Boolean(settings.value?.can_link_multiple) || !settings.value?.telegram_links?.length,
)
const showTokenField = computed(() => canManageBot.value && !hasToken.value)
const botDeepLink = computed(() => {
  const u = settings.value?.bot_username
  return u ? `https://t.me/${u}` : null
})

function fmt(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ru-RU')
  } catch {
    return iso
  }
}

async function loadSettings(): Promise<void> {
  const hadCache = settings.value != null
  if (!hadCache) loading.value = true
  try {
    const next = await getNotificationSettings()
    settings.value = next
    mutePhrases.value = [...(next.mute_phrases || [])]
    chatNotifications.setMutePhrases(mutePhrases.value)

    const [escalation, bot] = await Promise.all([
      next.can_manage_escalation ? getEscalationPolicy() : Promise.resolve(null),
      next.can_manage_bot ? getNotificationBot() : Promise.resolve(null),
    ])

    if (escalation) {
      escalationPolicy.value = escalation
      timeoutMinutes.value = escalation.timeout_minutes
    } else {
      escalationPolicy.value = null
      timeoutMinutes.value = 15
    }

    if (bot) {
      hasToken.value = bot.has_token
      if (bot.bot_username && settings.value) {
        settings.value.bot_username = bot.bot_username
        settings.value.bot_enabled = bot.is_enabled
      }
    } else {
      hasToken.value = true
    }

    if (!next.can_view_history) {
      activeTab.value = 'settings'
    } else {
      // Keep route tab — do not bounce settings → history after load.
      activeTab.value = tabFromRoute()
    }

    if (userId.value != null) {
      setNotificationSettingsCache(userId.value, {
        settings: settings.value,
        escalation,
        hasToken: hasToken.value,
      })
    }
  } catch (err) {
    if (!hadCache) {
      message.error(err instanceof AppError ? err.message : 'Не удалось загрузить')
    }
  } finally {
    loading.value = false
  }
}

async function loadHistory(): Promise<void> {
  if (settings.value && !canViewHistory.value) return
  const hadCache = historyItems.value.length > 0
  if (!hadCache) historyLoading.value = true
  try {
    const data = await getNotificationHistory({
      limit: 10,
      status: statusFilter.value || undefined,
    })
    historyItems.value = data.items
    if (userId.value != null) {
      setNotificationHistoryCache(userId.value, statusFilter.value, data.items)
    }
  } catch (err) {
    if (!hadCache) {
      message.error(err instanceof AppError ? err.message : 'Не удалось загрузить историю')
    }
  } finally {
    historyLoading.value = false
  }
}

async function onLink(): Promise<void> {
  const id = Number(telegramIdInput.value.trim())
  if (!Number.isFinite(id) || id <= 0) {
    message.warning('Введите числовой Telegram ID')
    return
  }
  linking.value = true
  try {
    await linkTelegram(id)
    telegramIdInput.value = ''
    message.success('Telegram привязан')
    await loadSettings()
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
    await loadSettings()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось отвязать')
  }
}

async function onSaveToken(): Promise<void> {
  const token = tokenInput.value.trim()
  if (!token) {
    message.warning('Введите токен бота')
    return
  }
  savingToken.value = true
  try {
    const bot = await patchNotificationBot({ bot_token: token, is_enabled: true })
    hasToken.value = bot.has_token
    tokenInput.value = ''
    if (settings.value) {
      settings.value.bot_username = bot.bot_username
      settings.value.bot_enabled = bot.is_enabled
    }
    message.success('Токен сохранён')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить токен')
  } finally {
    savingToken.value = false
  }
}

async function onSaveMutePhrases(): Promise<void> {
  savingMute.value = true
  try {
    settings.value = await patchMutePhrases(mutePhrases.value)
    mutePhrases.value = [...(settings.value.mute_phrases || [])]
    chatNotifications.setMutePhrases(mutePhrases.value)
    message.success('Фразы сохранены')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить фразы')
  } finally {
    savingMute.value = false
  }
}

async function onSaveEscalation(): Promise<void> {
  savingEscalation.value = true
  try {
    escalationPolicy.value = await patchEscalationPolicy({
      timeout_minutes: timeoutMinutes.value,
      mute_phrases: escalationPolicy.value?.mute_phrases ?? [],
    })
    timeoutMinutes.value = escalationPolicy.value.timeout_minutes
    message.success('Сохранено')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить')
  } finally {
    savingEscalation.value = false
  }
}

function onTabChange(name: string | number): void {
  const tab = name === 'history' ? 'history' : 'settings'
  activeTab.value = tab
  void router.replace({ query: { ...route.query, tab } })
  if (tab === 'history') {
    void loadHistory()
  }
}

watch(
  () => route.query.tab,
  () => {
    if (canViewHistory.value || settings.value == null) {
      activeTab.value = tabFromRoute()
    }
  },
)

onMounted(() => {
  hydrateFromCache()
  const preferHistory = tabFromRoute() === 'history'
  void Promise.all([
    loadSettings(),
    preferHistory ? loadHistory() : Promise.resolve(),
  ]).then(() => {
    if (canViewHistory.value && activeTab.value === 'history' && !historyItems.value.length) {
      void loadHistory()
    }
  })
})
</script>

<template>
  <section class="notif-page">
    <header class="notif-page__header">
      <h1>Уведомления</h1>
    </header>

    <NSpin :show="loading && !settings">
      <NTabs
        v-if="canViewHistory || (!settings && activeTab === 'history')"
        :value="activeTab"
        type="line"
        @update:value="onTabChange"
      >
        <NTabPane name="history" tab="История">
          <div class="notif-page__toolbar">
            <NSelect
              v-model:value="statusFilter"
              :options="statusOptions"
              style="width: 180px"
              @update:value="() => loadHistory()"
            />
          </div>
          <NSpin :show="historyLoading">
            <div v-if="!historyItems.length && !historyLoading" class="notif-page__empty">
              Пока нет записей
            </div>
            <div v-else class="hist__list">
              <article v-for="row in historyItems" :key="row.id" class="hist__row">
                <div class="hist__row-top">
                  <NTag :type="STATUS_TYPE[row.status] || 'default'" size="small">
                    {{ STATUS_LABEL[row.status] || row.status }}
                  </NTag>
                  <span class="hist__kind">{{ KIND_LABEL[row.kind] || row.kind }}</span>
                  <span class="hist__time">{{ fmt(row.created_at) }}</span>
                </div>
                <div class="hist__main">
                  <div>
                    <b>{{ row.target_user_name || `user #${row.target_user_id}` }}</b>
                    <span v-if="row.telegram_user_id" class="hist__muted">
                      · TG {{ row.telegram_user_id }}
                    </span>
                  </div>
                  <div v-if="row.contact_name">Контакт: {{ row.contact_name }}</div>
                  <div v-if="row.acked_at" class="hist__ok">Ознакомился: {{ fmt(row.acked_at) }}</div>
                  <div v-else-if="row.status === 'sent'" class="hist__warn">Ещё не ознакомился</div>
                </div>
              </article>
            </div>
          </NSpin>
        </NTabPane>

        <NTabPane name="settings" tab="Настройки">
          <div class="notif-page__settings">
            <NCard v-if="showTokenField" title="Токен бота" size="small" class="notif-page__card">
              <NSpace align="center">
                <NInput
                  v-model:value="tokenInput"
                  type="password"
                  show-password-on="click"
                  placeholder="123456:AA..."
                  style="max-width: 360px"
                />
                <NButton type="primary" :loading="savingToken" @click="onSaveToken">
                  Сохранить
                </NButton>
              </NSpace>
            </NCard>

            <NCard title="Telegram" size="small" class="notif-page__card">
              <p v-if="botDeepLink" class="notif-page__bot">
                <a :href="botDeepLink" target="_blank" rel="noopener">@{{ settings?.bot_username }}</a>
              </p>

              <div v-if="settings?.telegram_links?.length" class="notif-page__links">
                <div
                  v-for="link in settings.telegram_links"
                  :key="link.id"
                  class="notif-page__link-row"
                >
                  <NTag type="success" size="small">ID {{ link.telegram_user_id }}</NTag>
                  <span v-if="link.telegram_username" class="notif-page__muted">
                    @{{ link.telegram_username }}
                  </span>
                  <NButton size="tiny" quaternary type="error" @click="onUnlink(link.id)">
                    Отвязать
                  </NButton>
                </div>
              </div>

              <NSpace v-if="canLinkTelegram" align="center">
                <NInput
                  v-model:value="telegramIdInput"
                  placeholder="Telegram ID"
                  style="max-width: 220px"
                />
                <NButton type="primary" :loading="linking" @click="onLink">Привязать</NButton>
              </NSpace>
            </NCard>

            <NCard title="Без уведомлений" size="small" class="notif-page__card">
              <NDynamicTags v-model:value="mutePhrases" />
              <div class="notif-page__mute-actions">
                <NButton type="primary" :loading="savingMute" @click="onSaveMutePhrases">
                  Сохранить
                </NButton>
              </div>
            </NCard>

            <NCard
              v-if="canManageEscalation"
              title="Время эскалации"
              size="small"
              class="notif-page__card"
            >
              <NSpace align="center">
                <NInputNumber
                  v-model:value="timeoutMinutes"
                  :min="1"
                  :max="1440"
                  style="width: 140px"
                />
                <NButton type="primary" :loading="savingEscalation" @click="onSaveEscalation">
                  Сохранить
                </NButton>
              </NSpace>
            </NCard>
          </div>
        </NTabPane>
      </NTabs>

      <div v-else class="notif-page__settings">
        <NCard v-if="showTokenField" title="Токен бота" size="small" class="notif-page__card">
          <NSpace align="center">
            <NInput
              v-model:value="tokenInput"
              type="password"
              show-password-on="click"
              placeholder="123456:AA..."
              style="max-width: 360px"
            />
            <NButton type="primary" :loading="savingToken" @click="onSaveToken">Сохранить</NButton>
          </NSpace>
        </NCard>

        <NCard title="Telegram" size="small" class="notif-page__card">
          <p v-if="botDeepLink" class="notif-page__bot">
            <a :href="botDeepLink" target="_blank" rel="noopener">@{{ settings?.bot_username }}</a>
          </p>

          <div v-if="settings?.telegram_links?.length" class="notif-page__links">
            <div
              v-for="link in settings.telegram_links"
              :key="link.id"
              class="notif-page__link-row"
            >
              <NTag type="success" size="small">ID {{ link.telegram_user_id }}</NTag>
              <span v-if="link.telegram_username" class="notif-page__muted">
                @{{ link.telegram_username }}
              </span>
              <NButton size="tiny" quaternary type="error" @click="onUnlink(link.id)">
                Отвязать
              </NButton>
            </div>
          </div>

          <NSpace v-if="canLinkTelegram" align="center">
            <NInput
              v-model:value="telegramIdInput"
              placeholder="Telegram ID"
              style="max-width: 220px"
            />
            <NButton type="primary" :loading="linking" @click="onLink">Привязать</NButton>
          </NSpace>
        </NCard>

        <NCard title="Без уведомлений" size="small" class="notif-page__card">
          <NDynamicTags v-model:value="mutePhrases" />
          <div class="notif-page__mute-actions">
            <NButton type="primary" :loading="savingMute" @click="onSaveMutePhrases">
              Сохранить
            </NButton>
          </div>
        </NCard>

        <NCard
          v-if="canManageEscalation"
          title="Время эскалации"
          size="small"
          class="notif-page__card"
        >
          <NSpace align="center">
            <NInputNumber
              v-model:value="timeoutMinutes"
              :min="1"
              :max="1440"
              style="width: 140px"
            />
            <NButton type="primary" :loading="savingEscalation" @click="onSaveEscalation">
              Сохранить
            </NButton>
          </NSpace>
        </NCard>
      </div>
    </NSpin>
  </section>
</template>

<style scoped>
.notif-page__header {
  margin-bottom: 12px;
}
.notif-page__header h1 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}
.notif-page__toolbar {
  margin-bottom: 12px;
}
.notif-page__muted,
.notif-page__empty {
  color: var(--app-text-muted);
}
.notif-page__bot {
  margin: 0 0 12px;
}
.notif-page__bot a {
  font-weight: 600;
}
.notif-page__mute-actions {
  margin-top: 12px;
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
.hist__list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.hist__row {
  border: 1px solid var(--app-border, #e5e7eb);
  border-radius: 10px;
  padding: 12px 14px;
  background: var(--app-surface, transparent);
}
.hist__row-top {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.hist__kind {
  font-weight: 600;
}
.hist__time,
.hist__muted {
  color: var(--app-text-muted);
}
.hist__time {
  margin-left: auto;
  font-size: 0.85rem;
}
.hist__ok {
  color: var(--app-success, #16a34a);
}
.hist__warn {
  color: var(--app-warning, #ca8a04);
}
.hist__more {
  margin-top: 12px;
}
</style>
