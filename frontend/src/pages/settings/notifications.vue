<script setup lang="ts">
import {
  NButton,
  NCard,
  NDynamicTags,
  NForm,
  NFormItem,
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

import {
  getEscalationPolicy,
  getNotificationHistory,
  getNotificationSettings,
  linkTelegram,
  patchEscalationPolicy,
  type EscalationPolicy,
  type NotificationSettings,
  type StaffNotificationEvent,
  unlinkTelegram,
} from '@/features/notifications/api'
import { AppError } from '@/shared/api/http'

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
  cancelled: 'default',
  failed: 'error',
}

const STATUS_LABEL: Record<string, string> = {
  sent: 'Не ознакомлен',
  acked: 'Прочитано',
  cancelled: 'Отменено (ответ)',
  failed: 'Ошибка',
}

const SCOPE_TITLE: Record<string, string> = {
  org: 'Эскалация (все)',
  department: 'Эскалация (мой отдел)',
  group: 'Эскалация (моя группа)',
}

const SCOPE_HINT: Record<string, string> = {
  org: 'Настройка для всей организации. Учитывается последнее сохранение среди уровней.',
  department: 'Настройка для вашего отдела. Учитывается последнее сохранение среди уровней.',
  group: 'Настройка для вашей группы. Учитывается последнее сохранение среди уровней.',
}

const message = useMessage()
const route = useRoute()
const router = useRouter()

const loading = ref(true)
const saving = ref(false)
const linking = ref(false)
const settings = ref<NotificationSettings | null>(null)
const escalationPolicy = ref<EscalationPolicy | null>(null)
const telegramIdInput = ref('')
const timeoutMinutes = ref(15)
const mutePhrases = ref<string[]>([])

const activeTab = ref<'history' | 'settings'>('settings')

const historyLoading = ref(false)
const historyLoadingMore = ref(false)
const historyItems = ref<StaffNotificationEvent[]>([])
const historyCursor = ref<number | null>(null)
const statusFilter = ref('')

const statusOptions = [
  { label: 'Все', value: '' },
  { label: 'Не ознакомлен', value: 'sent' },
  { label: 'Прочитано', value: 'acked' },
  { label: 'Отменено', value: 'cancelled' },
  { label: 'Ошибка', value: 'failed' },
]

const canManageEscalation = computed(() => Boolean(settings.value?.can_manage_escalation))
const escalationTitle = computed(
  () => SCOPE_TITLE[escalationPolicy.value?.scope || ''] || 'Эскалация',
)
const escalationHint = computed(
  () =>
    SCOPE_HINT[escalationPolicy.value?.scope || ''] ||
    'Учитывается последнее сохранение среди уровней (организация / отдел / группа).',
)
const canViewHistory = computed(() => Boolean(settings.value?.can_view_history))
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
  loading.value = true
  try {
    settings.value = await getNotificationSettings()
    if (settings.value.can_manage_escalation) {
      escalationPolicy.value = await getEscalationPolicy()
      timeoutMinutes.value = escalationPolicy.value.timeout_minutes
      mutePhrases.value = [...escalationPolicy.value.mute_phrases]
    } else {
      escalationPolicy.value = null
      timeoutMinutes.value = 15
      mutePhrases.value = []
    }
    if (settings.value.can_view_history) {
      const tab = String(route.query.tab || '')
      activeTab.value = tab === 'settings' ? 'settings' : 'history'
    } else {
      activeTab.value = 'settings'
    }
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить')
  } finally {
    loading.value = false
  }
}

async function loadHistory(reset = true): Promise<void> {
  if (!canViewHistory.value) return
  if (reset) {
    historyLoading.value = true
    historyItems.value = []
    historyCursor.value = null
  } else {
    historyLoadingMore.value = true
  }
  try {
    const data = await getNotificationHistory({
      cursor: reset ? undefined : (historyCursor.value ?? undefined),
      limit: 40,
      status: statusFilter.value || undefined,
    })
    historyItems.value = reset ? data.items : [...historyItems.value, ...data.items]
    historyCursor.value = data.next_cursor
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить историю')
  } finally {
    historyLoading.value = false
    historyLoadingMore.value = false
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

async function onSaveEscalation(): Promise<void> {
  saving.value = true
  try {
    escalationPolicy.value = await patchEscalationPolicy({
      timeout_minutes: timeoutMinutes.value,
      mute_phrases: mutePhrases.value,
    })
    timeoutMinutes.value = escalationPolicy.value.timeout_minutes
    mutePhrases.value = [...escalationPolicy.value.mute_phrases]
    message.success('Сохранено')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить')
  } finally {
    saving.value = false
  }
}

function onTabChange(name: string | number): void {
  const tab = name === 'history' ? 'history' : 'settings'
  activeTab.value = tab
  void router.replace({ query: { ...route.query, tab } })
  if (tab === 'history' && !historyItems.value.length) {
    void loadHistory(true)
  }
}

watch(canViewHistory, (ok) => {
  if (ok && activeTab.value === 'history') {
    void loadHistory(true)
  }
})

onMounted(async () => {
  await loadSettings()
  if (canViewHistory.value && activeTab.value === 'history') {
    await loadHistory(true)
  }
})
</script>

<template>
  <section class="notif-page">
    <header class="notif-page__header">
      <h1>Уведомления</h1>
    </header>

    <NSpin :show="loading">
      <NTabs
        v-if="canViewHistory"
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
              @update:value="() => loadHistory(true)"
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
                  <div v-else-if="row.cancelled_at" class="hist__muted">
                    Отменено после ответа: {{ fmt(row.cancelled_at) }}
                  </div>
                  <div v-else-if="row.status === 'sent'" class="hist__warn">Ещё не ознакомился</div>
                </div>
              </article>
            </div>
            <div v-if="historyCursor" class="hist__more">
              <NButton :loading="historyLoadingMore" @click="loadHistory(false)">Ещё</NButton>
            </div>
          </NSpin>
        </NTabPane>

        <NTabPane name="settings" tab="Настройки">
          <NCard title="Telegram" size="small" class="notif-page__card">
            <p class="notif-page__hint">
              1. Откройте бота
              <template v-if="botDeepLink">
                —
                <a :href="botDeepLink" target="_blank" rel="noopener">@{{ settings?.bot_username }}</a>
              </template>
              <template v-else-if="!settings?.bot_enabled">(ещё не настроен)</template>.
              <br />
              2. Нажмите <b>Start</b> — бот пришлёт ваш ID.
              <br />
              3. Вставьте ID и нажмите «Привязать».
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

            <NSpace
              v-if="settings?.can_link_multiple || !settings?.telegram_links?.length"
              align="center"
            >
              <NInput
                v-model:value="telegramIdInput"
                placeholder="Telegram ID"
                style="max-width: 220px"
              />
              <NButton type="primary" :loading="linking" @click="onLink">Привязать</NButton>
            </NSpace>
            <p v-else class="notif-page__muted">
              Можно привязать только один Telegram. Отвяжите текущий, чтобы заменить.
            </p>
          </NCard>

          <NCard
            v-if="canManageEscalation"
            :title="escalationTitle"
            size="small"
            class="notif-page__card"
          >
            <p class="notif-page__hint">{{ escalationHint }}</p>
            <NForm label-placement="top">
              <NFormItem label="Нет ответа, мин">
                <NInputNumber
                  v-model:value="timeoutMinutes"
                  :min="1"
                  :max="1440"
                  style="width: 100%"
                />
              </NFormItem>
              <NFormItem label="Не уведомлять по фразам">
                <NDynamicTags v-model:value="mutePhrases" />
              </NFormItem>
              <NButton type="primary" :loading="saving" @click="onSaveEscalation">
                Сохранить
              </NButton>
            </NForm>
          </NCard>
        </NTabPane>
      </NTabs>

      <template v-else>
        <NCard title="Telegram" size="small" class="notif-page__card">
          <p class="notif-page__hint">
            1. Откройте бота
            <template v-if="botDeepLink">
              —
              <a :href="botDeepLink" target="_blank" rel="noopener">@{{ settings?.bot_username }}</a>
            </template>
            <template v-else-if="!settings?.bot_enabled">(ещё не настроен)</template>.
            <br />
            2. Нажмите <b>Start</b> — бот пришлёт ваш ID.
            <br />
            3. Вставьте ID и нажмите «Привязать».
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

          <NSpace
            v-if="settings?.can_link_multiple || !settings?.telegram_links?.length"
            align="center"
          >
            <NInput
              v-model:value="telegramIdInput"
              placeholder="Telegram ID"
              style="max-width: 220px"
            />
            <NButton type="primary" :loading="linking" @click="onLink">Привязать</NButton>
          </NSpace>
          <p v-else class="notif-page__muted">
            Можно привязать только один Telegram. Отвяжите текущий, чтобы заменить.
          </p>
        </NCard>

        <NCard
          v-if="canManageEscalation"
          :title="escalationTitle"
          size="small"
          class="notif-page__card"
        >
          <p class="notif-page__hint">{{ escalationHint }}</p>
          <NForm label-placement="top">
            <NFormItem label="Нет ответа, мин">
              <NInputNumber
                v-model:value="timeoutMinutes"
                :min="1"
                :max="1440"
                style="width: 100%"
              />
            </NFormItem>
            <NFormItem label="Не уведомлять по фразам">
              <NDynamicTags v-model:value="mutePhrases" />
            </NFormItem>
            <NButton type="primary" :loading="saving" @click="onSaveEscalation">Сохранить</NButton>
          </NForm>
        </NCard>
      </template>
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
.notif-page__hint,
.notif-page__muted,
.notif-page__empty {
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
