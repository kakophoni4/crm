<script setup lang="ts">
import { Delete, History, PhoneCall, PhoneOff, RotateCcw, Wifi } from 'lucide-vue-next'
import { NButton, NIcon, NSelect, NSpin, NTag, useMessage } from 'naive-ui'
import type { SelectOption } from 'naive-ui'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import {
  getTelephonyWebrtcConfig,
  listTelephonyAccounts,
  type TelephonyAccount,
} from '@/features/telephony/api'
import { CrmSoftphone, type SoftphoneStatus } from '@/features/telephony/softphone'
import { AppError } from '@/shared/api/http'

const message = useMessage()
const TELEPHONY_HISTORY_KEY = 'crm.telephony.call_history'

type CallHistoryStatus = 'calling' | 'answered' | 'completed' | 'failed'

interface CallHistoryItem {
  id: string
  number: string
  accountName: string
  startedAt: string
  durationSeconds: number | null
  status: CallHistoryStatus
}

const loading = ref(false)
const connecting = ref(false)
const calling = ref(false)
const accounts = ref<TelephonyAccount[]>([])
const selectedAccountId = ref<number | null>(null)
const dialNumber = ref('')
const status = ref<SoftphoneStatus>('idle')
const remoteAudio = ref<HTMLAudioElement | null>(null)
const callHistory = ref<CallHistoryItem[]>([])
const activeCallId = ref<string | null>(null)

const softphone = new CrmSoftphone({
  onStatus: (value) => {
    status.value = value
  },
  onError: (value) => {
    message.error(value)
  },
})

const activeAccounts = computed(() => accounts.value.filter((account) => account.is_active))
const selectedAccount = computed(
  () => activeAccounts.value.find((account) => account.id === selectedAccountId.value) ?? null,
)
const accountOptions = computed<SelectOption[]>(() =>
  activeAccounts.value.map((account) => ({
    label: account.group_name ? `${account.name} · ${account.group_name}` : account.name,
    value: account.id,
  })),
)
const statusLabel = computed(() => {
  const labels: Record<SoftphoneStatus, string> = {
    idle: 'Отключено',
    connecting: 'Подключение',
    registered: 'Готово',
    calling: 'Вызов',
    'in-call': 'Разговор',
    ended: 'Завершено',
  }
  return labels[status.value]
})
const canCall = computed(
  () => status.value === 'registered' && dialNumber.value.trim().length > 0 && !calling.value,
)
const connectionTagType = computed(() =>
  status.value === 'registered' || status.value === 'in-call' ? 'success' : 'default',
)
const hasHistory = computed(() => callHistory.value.length > 0)

const dialKeys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '+', '0', '#']

function appendDigit(value: string): void {
  dialNumber.value = `${dialNumber.value}${value}`
}

function backspace(): void {
  dialNumber.value = dialNumber.value.slice(0, -1)
}

function redial(number: string): void {
  dialNumber.value = number
}

function loadCallHistory(): void {
  try {
    const raw = window.localStorage.getItem(TELEPHONY_HISTORY_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    callHistory.value = Array.isArray(parsed) ? parsed.slice(0, 20) : []
  } catch {
    callHistory.value = []
  }
}

function saveCallHistory(): void {
  window.localStorage.setItem(
    TELEPHONY_HISTORY_KEY,
    JSON.stringify(callHistory.value.slice(0, 20)),
  )
}

function addCallHistoryItem(number: string): void {
  const item: CallHistoryItem = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    number,
    accountName: selectedAccount.value?.name ?? 'Телефония',
    startedAt: new Date().toISOString(),
    durationSeconds: null,
    status: 'calling',
  }
  activeCallId.value = item.id
  callHistory.value = [item, ...callHistory.value].slice(0, 20)
  saveCallHistory()
}

function updateActiveCall(statusValue: CallHistoryStatus): void {
  const id = activeCallId.value
  if (!id) return
  callHistory.value = callHistory.value.map((item) => {
    if (item.id !== id) return item
    const durationSeconds =
      statusValue === 'completed' || statusValue === 'failed'
        ? Math.max(0, Math.round((Date.now() - Date.parse(item.startedAt)) / 1000))
        : item.durationSeconds
    return { ...item, status: statusValue, durationSeconds }
  })
  if (statusValue === 'completed' || statusValue === 'failed') {
    activeCallId.value = null
  }
  saveCallHistory()
}

function formatCallTime(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—'
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}

function callStatusLabel(value: CallHistoryStatus): string {
  const labels: Record<CallHistoryStatus, string> = {
    calling: 'Вызов',
    answered: 'Разговор',
    completed: 'Завершён',
    failed: 'Ошибка',
  }
  return labels[value]
}

async function load(): Promise<void> {
  loading.value = true
  try {
    accounts.value = await listTelephonyAccounts()
    selectedAccountId.value = activeAccounts.value[0]?.id ?? null
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить телефонию')
  } finally {
    loading.value = false
  }
}

async function connectSoftphone(): Promise<void> {
  if (!selectedAccount.value) {
    message.warning('Выберите SIP-аккаунт')
    return
  }
  if (!remoteAudio.value) {
    message.error('Аудио-элемент еще не готов')
    return
  }
  connecting.value = true
  try {
    const config = await getTelephonyWebrtcConfig(selectedAccount.value.id)
    if (config.extension_created) {
      message.info('Extension создан, ждем синхронизацию Asterisk')
      await sleep(6500)
    }
    await softphone.connect(config, remoteAudio.value)
    message.success(`SIP ${config.extension} зарегистрирован`)
  } catch (err) {
    status.value = 'idle'
    message.error(err instanceof AppError ? err.message : 'Не удалось подключить SIP')
  } finally {
    connecting.value = false
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

async function startCall(): Promise<void> {
  if (!canCall.value) {
    message.warning('Сначала подключите SIP и введите номер')
    return
  }
  const number = dialNumber.value.trim()
  addCallHistoryItem(number)
  calling.value = true
  try {
    await softphone.call(number)
  } catch (err) {
    status.value = 'registered'
    updateActiveCall('failed')
    message.error(err instanceof Error ? err.message : 'Не удалось начать звонок')
  } finally {
    calling.value = false
  }
}

async function hangup(): Promise<void> {
  try {
    await softphone.hangup()
    updateActiveCall('completed')
  } catch (err) {
    message.error(err instanceof Error ? err.message : 'Не удалось завершить звонок')
  }
}

onMounted(() => {
  loadCallHistory()
  void load()
})

onBeforeUnmount(() => {
  void softphone.disconnect()
})

watch(status, (value) => {
  if (value === 'in-call') updateActiveCall('answered')
  if (value === 'ended') updateActiveCall('completed')
})
</script>

<template>
  <section class="telephony-page">
    <header class="telephony-page__header">
      <div>
        <h1 class="telephony-page__title">Телефония</h1>
        <p class="telephony-page__hint">Набор номера и последние вызовы.</p>
      </div>
      <NTag :type="connectionTagType">
        {{ statusLabel }}
      </NTag>
    </header>

    <NSpin :show="loading">
      <div class="telephony-workspace">
        <section class="telephony-dialer" aria-label="Dialer">
          <NSelect
            v-model:value="selectedAccountId"
            :options="accountOptions"
            placeholder="SIP-аккаунт"
            filterable
            :disabled="status === 'registered' || status === 'in-call'"
          />

          <div class="telephony-dialer__display">
            <span v-if="dialNumber">{{ dialNumber }}</span>
            <span v-else class="telephony-dialer__placeholder">+7 900 000-00-00</span>
            <NButton circle quaternary aria-label="Backspace" @click="backspace">
              <template #icon>
                <NIcon><Delete /></NIcon>
              </template>
            </NButton>
          </div>

          <div class="telephony-dialer__keys">
            <NButton
              v-for="key in dialKeys"
              :key="key"
              size="large"
              class="telephony-dialer__key"
              @click="appendDigit(key)"
            >
              {{ key }}
            </NButton>
          </div>

          <div class="telephony-dialer__actions">
            <NButton
              type="default"
              size="large"
              :loading="connecting"
              :disabled="!selectedAccount || status === 'registered' || status === 'in-call'"
              @click="connectSoftphone"
            >
              <template #icon>
                <NIcon><Wifi /></NIcon>
              </template>
              Подключить
            </NButton>
            <NButton type="primary" size="large" :disabled="!canCall" @click="startCall">
              <template #icon>
                <NIcon><PhoneCall /></NIcon>
              </template>
              Позвонить
            </NButton>
            <NButton
              type="error"
              size="large"
              :disabled="status !== 'calling' && status !== 'in-call'"
              @click="hangup"
            >
              <template #icon>
                <NIcon><PhoneOff /></NIcon>
              </template>
            </NButton>
          </div>

          <div class="telephony-dialer__connection">
            <span>{{ selectedAccount?.name ?? 'Линия не выбрана' }}</span>
            <NTag size="small" :type="connectionTagType">{{ statusLabel }}</NTag>
          </div>
        </section>

        <section class="telephony-history" aria-label="Call history">
          <header class="telephony-history__header">
            <div>
              <h2>История вызовов</h2>
              <p>Последние звонки с этого рабочего места.</p>
            </div>
            <NIcon :size="22"><History /></NIcon>
          </header>

          <div v-if="hasHistory" class="telephony-history__list">
            <div v-for="item in callHistory" :key="item.id" class="telephony-history__item">
              <div class="telephony-history__main">
                <strong>{{ item.number }}</strong>
                <span>{{ item.accountName }} · {{ formatCallTime(item.startedAt) }}</span>
              </div>
              <div class="telephony-history__meta">
                <NTag size="small" :type="item.status === 'failed' ? 'error' : 'default'">
                  {{ callStatusLabel(item.status) }}
                </NTag>
                <span>{{ formatDuration(item.durationSeconds) }}</span>
                <NButton circle quaternary size="small" aria-label="Повторить" @click="redial(item.number)">
                  <template #icon>
                    <NIcon><RotateCcw /></NIcon>
                  </template>
                </NButton>
              </div>
            </div>
          </div>
          <div v-else class="telephony-history__empty">
            <NIcon><History /></NIcon>
            <span>Здесь появятся последние вызовы.</span>
          </div>
          <audio ref="remoteAudio" autoplay />
        </section>
      </div>
    </NSpin>
  </section>
</template>

<style scoped>
.telephony-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.telephony-page__header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
}

.telephony-page__title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}

.telephony-page__hint {
  margin: 6px 0 0;
  color: var(--app-text-muted);
}

.telephony-workspace {
  display: grid;
  grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
  gap: 16px;
}

.telephony-dialer,
.telephony-history {
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  border-radius: 8px;
  padding: 16px;
}

.telephony-dialer {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.telephony-dialer__display {
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 8px 0 14px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  font-size: 1.125rem;
  font-weight: 700;
}

.telephony-dialer__placeholder {
  color: var(--app-text-muted);
  font-weight: 500;
}

.telephony-dialer__keys {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.telephony-dialer__key {
  min-height: 44px;
}

.telephony-dialer__actions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 48px;
  gap: 8px;
}

.telephony-dialer__connection {
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--app-text-muted);
  font-size: 0.875rem;
}

.telephony-history {
  min-height: 320px;
}

.telephony-history__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.telephony-history__header h2 {
  margin: 0;
  font-size: 1.125rem;
}

.telephony-history__header p {
  margin: 4px 0 0;
  color: var(--app-text-muted);
  font-size: 0.875rem;
}

.telephony-history__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.telephony-history__item {
  min-height: 54px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
}

.telephony-history__main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.telephony-history__main strong {
  font-size: 0.95rem;
}

.telephony-history__main span,
.telephony-history__meta span {
  color: var(--app-text-muted);
  font-size: 0.8125rem;
}

.telephony-history__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.telephony-history__empty {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 220px;
  justify-content: center;
  color: var(--app-text-muted);
}

@media (max-width: 900px) {
  .telephony-workspace {
    grid-template-columns: 1fr;
  }

  .telephony-dialer__actions {
    grid-template-columns: 1fr;
  }
}
</style>
