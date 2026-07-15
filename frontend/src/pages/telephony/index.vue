<script setup lang="ts">
import { Delete, History, Mic, MicOff, PhoneCall, PhoneOff, RotateCcw, UserPlus, Volume2, Wifi } from 'lucide-vue-next'
import { NButton, NIcon, NSelect, NSpin, NTag, useMessage } from 'naive-ui'
import type { SelectOption } from 'naive-ui'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import type { Contact } from '@/entities/contact/types'
import CreateContactDialog from '@/features/contacts/CreateContactDialog.vue'
import {
  createTelephonyCall,
  getTelephonyWebrtcConfig,
  listTelephonyAccounts,
  listTelephonyCalls,
  updateTelephonyCall,
  type TelephonyAccount,
  type TelephonyCall,
  type TelephonyCallStatus,
  type TelephonyWebrtcConfig,
} from '@/features/telephony/api'
import { CrmSoftphone, mapMediaError, type SoftphoneStatus } from '@/features/telephony/softphone'
import { AppError } from '@/shared/api/http'
import { normalizeRussianPhone } from '@/shared/lib/phone'

const message = useMessage()
const router = useRouter()

const loading = ref(false)
const historyLoading = ref(false)
const connecting = ref(false)
const calling = ref(false)
const autoConnectAttempted = ref(false)
const accounts = ref<TelephonyAccount[]>([])
const selectedAccountId = ref<number | null>(null)
const dialDigits = ref('')
const status = ref<SoftphoneStatus>('idle')
const remoteAudio = ref<HTMLAudioElement | null>(null)
const callHistory = ref<TelephonyCall[]>([])
const activeCallId = ref<number | null>(null)
const activeCallStartedAt = ref<number | null>(null)
const activeElapsedSeconds = ref(0)
const activeCallAnswered = ref(false)
const muted = ref(false)
const audioPrimed = ref(false)
const contactModalVisible = ref(false)
const contactModalPhone = ref('')
const contactDepartmentId = ref<number | null>(null)
let callTimer: number | null = null
let ringbackContext: AudioContext | null = null
let ringbackGain: GainNode | null = null
let ringbackTimer: number | null = null
let ringbackOscillators: OscillatorNode[] = []

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
    label: account.group_name ? `${account.name} - ${account.group_name}` : account.name,
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
const fullNumber = computed(() => `+7${dialDigits.value}`)
const displayNumber = computed(() => formatRussianNumber(dialDigits.value))
const canCall = computed(
  () => status.value === 'registered' && dialDigits.value.length === 10 && !calling.value,
)
const connectionTagType = computed(() =>
  status.value === 'registered' || status.value === 'in-call' ? 'success' : 'default',
)
const hasHistory = computed(() => callHistory.value.length > 0)
const activeCall = computed(
  () => callHistory.value.find((item) => item.id === activeCallId.value) ?? null,
)
const callPanelVisible = computed(
  () => activeCall.value != null && (status.value === 'calling' || status.value === 'in-call'),
)
const canCreateContactFromDial = computed(() => dialDigits.value.length === 10)

const dialKeys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0']

function appendDigit(value: string): void {
  if (!/^\d$/.test(value) || dialDigits.value.length >= 10) return
  dialDigits.value = `${dialDigits.value}${value}`
}

function backspace(): void {
  dialDigits.value = dialDigits.value.slice(0, -1)
}

function redial(number: string): void {
  const digits = number.replace(/\D/g, '')
  if (digits.length === 11 && digits.startsWith('7')) {
    dialDigits.value = digits.slice(1, 11)
    return
  }
  if (digits.length === 10) {
    dialDigits.value = digits
  }
}

function formatRussianNumber(digits: string): string {
  const padded = digits.padEnd(10, '0')
  const chunks = [
    padded.slice(0, 3),
    padded.slice(3, 6),
    padded.slice(6, 8),
    padded.slice(8, 10),
  ]
  return `+7 ${chunks[0]} ${chunks[1]}-${chunks[2]}-${chunks[3]}`
}

function openContactModal(phone: string, departmentId?: number | null): void {
  const normalizedPhone = normalizeRussianPhone(phone)
  if (!normalizedPhone) {
    message.warning('Введите полный номер: 10 цифр после +7')
    return
  }
  contactModalPhone.value = normalizedPhone
  contactDepartmentId.value = departmentId ?? selectedAccount.value?.department_id ?? null
  contactModalVisible.value = true
}

function onTelephonyContactCreated(contact: Contact): void {
  const chatId = contact.workspace?.chat_id
  if (chatId == null) return
  void router.push({ name: 'chats', query: { chatId: String(chatId) } })
}

function formatCallTime(value: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '-'
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}

function activeCallStatusLabel(): string {
  if (muted.value) return 'Микрофон выключен'
  if (status.value === 'in-call') return 'Разговор'
  return 'Идёт вызов'
}

function callStatusLabel(value: TelephonyCallStatus): string {
  const labels: Record<TelephonyCallStatus, string> = {
    calling: 'Вызов',
    answered: 'Разговор',
    completed: 'Завершён',
    failed: 'Ошибка',
  }
  return labels[value]
}

function callOwnerLabel(item: TelephonyCall): string {
  const parts = [item.account_name]
  if (item.user_name) parts.push(item.user_name)
  return parts.join(' - ')
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [accountItems, callItems] = await Promise.all([
      listTelephonyAccounts(),
      listTelephonyCalls(),
    ])
    accounts.value = accountItems
    callHistory.value = callItems
    selectedAccountId.value = activeAccounts.value[0]?.id ?? null
    if (selectedAccountId.value != null && !autoConnectAttempted.value) {
      autoConnectAttempted.value = true
      void connectSoftphone({ silent: true })
    }
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить телефонию')
  } finally {
    loading.value = false
  }
}

async function refreshHistory(): Promise<void> {
  historyLoading.value = true
  try {
    callHistory.value = await listTelephonyCalls()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось обновить историю')
  } finally {
    historyLoading.value = false
  }
}

async function connectSoftphone(options: { silent?: boolean } = {}): Promise<void> {
  const account = selectedAccount.value
  if (!account) {
    if (!options.silent) message.warning('Выберите SIP-аккаунт')
    return
  }
  if (!remoteAudio.value) {
    if (!options.silent) message.error('Аудио ещё не готово')
    return
  }
  if (status.value === 'registered' || status.value === 'in-call' || connecting.value) {
    return
  }
  connecting.value = true
  try {
    const config = await getTelephonyWebrtcConfig(account.id)
    if (config.extension_created) {
      if (!options.silent) {
        message.info('Линия создана, ждём синхронизацию Asterisk')
      }
      await sleep(5000)
    }
    await connectWithRetry(config, remoteAudio.value, config.extension_created ? 5 : 3)
    if (!options.silent) message.success(`Линия ${config.extension} подключена`)
  } catch (err) {
    status.value = 'idle'
    if (!options.silent) {
      message.error(
        err instanceof AppError
          ? err.message
          : mapMediaError(err instanceof Error ? err : new Error('Не удалось подключить SIP')),
      )
    }
  } finally {
    connecting.value = false
  }
}

async function connectWithRetry(
  config: TelephonyWebrtcConfig,
  audio: HTMLAudioElement,
  attempts: number,
): Promise<void> {
  let lastError: unknown = null
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      await softphone.connect(config, audio)
      return
    } catch (err) {
      lastError = err
      if (attempt < attempts) {
        await sleep(2500)
      }
    }
  }
  throw lastError instanceof Error ? lastError : new Error('SIP registration failed')
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function activeDuration(): number | null {
  if (activeCallStartedAt.value == null) return null
  return Math.max(0, Math.round((Date.now() - activeCallStartedAt.value) / 1000))
}

function startCallTimer(): void {
  stopCallTimer()
  activeElapsedSeconds.value = activeDuration() ?? 0
  callTimer = window.setInterval(() => {
    activeElapsedSeconds.value = activeDuration() ?? 0
  }, 1000)
}

function stopCallTimer(): void {
  if (callTimer == null) return
  window.clearInterval(callTimer)
  callTimer = null
}

function audioContextCtor(): typeof AudioContext | null {
  const win = window as Window & { webkitAudioContext?: typeof AudioContext }
  return window.AudioContext ?? win.webkitAudioContext ?? null
}

function ensureRingbackContext(): AudioContext | null {
  if (ringbackContext) return ringbackContext
  const Ctor = audioContextCtor()
  if (!Ctor) return null
  ringbackContext = new Ctor()
  ringbackGain = ringbackContext.createGain()
  ringbackGain.gain.value = 0.045
  ringbackGain.connect(ringbackContext.destination)
  return ringbackContext
}

function stopRingbackTone(): void {
  for (const oscillator of ringbackOscillators) {
    try {
      oscillator.stop()
    } catch {
    }
    oscillator.disconnect()
  }
  ringbackOscillators = []
}

function playRingbackTone(): void {
  const context = ensureRingbackContext()
  if (!context || !ringbackGain || ringbackOscillators.length > 0) return
  const tones = [425, 450]
  ringbackOscillators = tones.map((frequency) => {
    const oscillator = context.createOscillator()
    oscillator.type = 'sine'
    oscillator.frequency.value = frequency
    oscillator.connect(ringbackGain as GainNode)
    oscillator.start()
    return oscillator
  })
}

function startRingback(): void {
  const context = ensureRingbackContext()
  if (!context || ringbackTimer != null) return
  void context.resume().catch(() => undefined)
  playRingbackTone()
  window.setTimeout(stopRingbackTone, 900)
  ringbackTimer = window.setInterval(() => {
    playRingbackTone()
    window.setTimeout(stopRingbackTone, 900)
  }, 3500)
}

function stopRingback(): void {
  if (ringbackTimer != null) {
    window.clearInterval(ringbackTimer)
    ringbackTimer = null
  }
  stopRingbackTone()
}

async function updateActiveCall(statusValue: TelephonyCallStatus): Promise<void> {
  const id = activeCallId.value
  if (id == null) return
  const finalStatus = statusValue === 'completed' || statusValue === 'failed'
  const durationSeconds = finalStatus ? activeDuration() : null
  try {
    const updated = await updateTelephonyCall(id, statusValue, durationSeconds)
    callHistory.value = callHistory.value.map((item) => (item.id === id ? updated : item))
  } catch {
    await refreshHistory()
  }
  if (finalStatus) {
    activeCallId.value = null
    activeCallStartedAt.value = null
    activeCallAnswered.value = false
    activeElapsedSeconds.value = 0
    muted.value = false
    stopCallTimer()
    stopRingback()
  }
}

async function startCall(): Promise<void> {
  if (!canCall.value || selectedAccountId.value == null) {
    message.warning('Подключите линию и введите 10 цифр номера')
    return
  }
  primeRemoteAudio()
  calling.value = true
  try {
    // Mic first — без микрофона INVITE не шлём и запись звонка не создаём.
    await softphone.ensureLocalMic()
    const call = await createTelephonyCall(selectedAccountId.value, fullNumber.value)
    activeCallId.value = call.id
    activeCallStartedAt.value = Date.parse(call.started_at)
    activeCallAnswered.value = false
    muted.value = false
    startCallTimer()
    startRingback()
    callHistory.value = [call, ...callHistory.value.filter((item) => item.id !== call.id)]
    await softphone.call(call.phone_number)
  } catch (err) {
    stopRingback()
    if (activeCallId.value != null) {
      await updateActiveCall('failed')
    }
    status.value = 'registered'
    const text =
      err instanceof Error ? err.message : 'Не удалось начать звонок'
    message.error(text)
  } finally {
    calling.value = false
  }
}

async function hangup(): Promise<void> {
  try {
    await softphone.hangup()
  } catch (err) {
    message.error(err instanceof Error ? err.message : 'Не удалось завершить звонок')
  }
}

function toggleMute(): void {
  if (!callPanelVisible.value) return
  if (muted.value) {
    softphone.unmute()
    muted.value = false
  } else {
    softphone.mute()
    muted.value = true
  }
}

function bindRemoteAudio(): void {
  if (!remoteAudio.value) return
  const stream = softphone.getRemoteMediaStream()
  if (stream && remoteAudio.value.srcObject !== stream) {
    remoteAudio.value.srcObject = stream
  }
}

function primeRemoteAudio(): void {
  if (!remoteAudio.value || audioPrimed.value) return
  remoteAudio.value.muted = false
  remoteAudio.value.volume = 1
  if (!remoteAudio.value.srcObject) {
    remoteAudio.value.srcObject = new MediaStream()
  }
  void remoteAudio.value.play().then(() => {
    audioPrimed.value = true
  }).catch(() => {
    audioPrimed.value = false
  })
}

function enableRemoteAudio(options: { silent?: boolean } = {}): void {
  if (!remoteAudio.value) return
  bindRemoteAudio()
  remoteAudio.value.muted = false
  remoteAudio.value.volume = 1
  void remoteAudio.value.play().catch(() => {
    if (!options.silent) {
      message.warning('Браузер не дал включить звук автоматически')
    }
  })
}

function handleKeydown(event: KeyboardEvent): void {
  const target = event.target as HTMLElement | null
  const tag = target?.tagName.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || target?.isContentEditable) return
  if (/^\d$/.test(event.key)) {
    appendDigit(event.key)
    event.preventDefault()
  } else if (event.key === 'Backspace') {
    backspace()
    event.preventDefault()
  } else if (event.key === 'Enter') {
    primeRemoteAudio()
    void startCall()
    event.preventDefault()
  } else if (event.key === 'Escape') {
    void hangup()
    event.preventDefault()
  }
}

onMounted(() => {
  void load()
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  stopCallTimer()
  stopRingback()
  void softphone.disconnect()
})

watch(status, (value) => {
  if (value === 'in-call') {
    stopRingback()
    activeCallAnswered.value = true
    enableRemoteAudio({ silent: true })
    void updateActiveCall('answered')
  }
  if (value === 'ended') {
    stopRingback()
    void (async () => {
      await updateActiveCall(activeCallAnswered.value ? 'completed' : 'failed')
      stopCallTimer()
      muted.value = false
      if (status.value === 'ended') status.value = 'registered'
    })()
  }
})
</script>

<template>
  <section class="telephony-page">
    <header class="telephony-page__header">
      <div>
        <h1 class="telephony-page__title">Телефония</h1>
      </div>
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
            <span :class="{ 'telephony-dialer__placeholder': dialDigits.length === 0 }">
              {{ displayNumber }}
            </span>
            <NButton circle quaternary aria-label="Стереть" @click="backspace">
              <template #icon>
                <NIcon><Delete /></NIcon>
              </template>
            </NButton>
          </div>

          <div v-if="callPanelVisible && activeCall" class="telephony-active-call">
            <div class="telephony-active-call__main">
              <span>{{ activeCallStatusLabel() }}</span>
              <strong>{{ activeCall.phone_number }}</strong>
              <small>{{ formatDuration(activeElapsedSeconds) }}</small>
            </div>
            <div class="telephony-active-call__actions">
              <NButton
                circle
                secondary
                :type="muted ? 'warning' : 'default'"
                :aria-label="muted ? 'Включить микрофон' : 'Выключить микрофон'"
                @click="toggleMute"
              >
                <template #icon>
                  <NIcon>
                    <MicOff v-if="muted" />
                    <Mic v-else />
                  </NIcon>
                </template>
              </NButton>
              <NButton circle secondary aria-label="Включить звук" @click="() => enableRemoteAudio()">
                <template #icon>
                  <NIcon><Volume2 /></NIcon>
                </template>
              </NButton>
              <NButton circle type="error" aria-label="Сбросить" @click="hangup">
                <template #icon>
                  <NIcon><PhoneOff /></NIcon>
                </template>
              </NButton>
            </div>
          </div>

          <div class="telephony-dialer__keys">
            <NButton
              v-for="key in dialKeys"
              :key="key"
              size="large"
              class="telephony-dialer__key"
              :class="{ 'telephony-dialer__key--zero': key === '0' }"
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
              @click="() => connectSoftphone()"
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

          <NButton
            secondary
            size="large"
            :disabled="!canCreateContactFromDial"
            @click="openContactModal(fullNumber, selectedAccount?.department_id)"
          >
            <template #icon>
              <NIcon><UserPlus /></NIcon>
            </template>
            Создать контакт
          </NButton>

          <div class="telephony-dialer__connection">
            <span>{{ selectedAccount?.name ?? 'Линия не выбрана' }}</span>
            <NTag size="small" :type="connectionTagType">{{ statusLabel }}</NTag>
          </div>
        </section>

        <section class="telephony-history" aria-label="Call history">
          <header class="telephony-history__header">
            <div>
              <h2>История вызовов</h2>
            </div>
            <NButton circle quaternary :loading="historyLoading" aria-label="Обновить" @click="refreshHistory">
              <template #icon>
                <NIcon :size="22"><History /></NIcon>
              </template>
            </NButton>
          </header>

          <div v-if="hasHistory" class="telephony-history__list">
            <div v-for="item in callHistory" :key="item.id" class="telephony-history__item">
              <div class="telephony-history__main">
                <strong>{{ item.phone_number }}</strong>
                <span>{{ callOwnerLabel(item) }} - {{ formatCallTime(item.started_at) }}</span>
              </div>
              <div class="telephony-history__meta">
                <NTag size="small" :type="item.status === 'failed' ? 'error' : 'default'">
                  {{ callStatusLabel(item.status) }}
                </NTag>
                <span>{{ formatDuration(item.duration_seconds) }}</span>
                <NButton circle quaternary size="small" aria-label="Повторить" @click="redial(item.phone_number)">
                  <template #icon>
                    <NIcon><RotateCcw /></NIcon>
                  </template>
                </NButton>
                <NButton
                  circle
                  quaternary
                  size="small"
                  aria-label="Создать контакт"
                  @click="openContactModal(item.phone_number, item.department_id)"
                >
                  <template #icon>
                    <NIcon><UserPlus /></NIcon>
                  </template>
                </NButton>
              </div>
            </div>
          </div>
          <div v-else class="telephony-history__empty">
            <NIcon><History /></NIcon>
            <span>Здесь появятся последние вызовы.</span>
          </div>
          <audio ref="remoteAudio" autoplay playsinline />
        </section>
      </div>
    </NSpin>

    <div v-if="callPanelVisible && activeCall" class="telephony-floating-call">
      <div class="telephony-floating-call__body">
        <span>{{ activeCallStatusLabel() }}</span>
        <strong>{{ activeCall.phone_number }}</strong>
        <small>{{ formatDuration(activeElapsedSeconds) }}</small>
      </div>
      <NButton
        circle
        secondary
        :type="muted ? 'warning' : 'default'"
        :aria-label="muted ? 'Включить микрофон' : 'Выключить микрофон'"
        @click="toggleMute"
      >
        <template #icon>
          <NIcon>
            <MicOff v-if="muted" />
            <Mic v-else />
          </NIcon>
        </template>
      </NButton>
      <NButton circle secondary aria-label="Включить звук" @click="() => enableRemoteAudio()">
        <template #icon>
          <NIcon><Volume2 /></NIcon>
        </template>
      </NButton>
      <NButton circle type="error" aria-label="Сбросить" @click="hangup">
        <template #icon>
          <NIcon><PhoneOff /></NIcon>
        </template>
      </NButton>
    </div>

    <CreateContactDialog
      v-model:show="contactModalVisible"
      :initial-phone="contactModalPhone"
      :department-id="contactDepartmentId"
      source="telephony"
      require-phone
      @created="onTelephonyContactCreated"
    />
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

.telephony-dialer__key--zero {
  grid-column: 2;
}

.telephony-active-call {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: 1px solid rgba(99, 226, 183, 0.45);
  border-radius: 8px;
  background: rgba(99, 226, 183, 0.08);
}

.telephony-active-call__main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.telephony-active-call__main span,
.telephony-active-call__main small,
.telephony-floating-call__body span,
.telephony-floating-call__body small {
  color: var(--app-text-muted);
  font-size: 0.8125rem;
}

.telephony-active-call__main strong,
.telephony-floating-call__body strong {
  font-size: 1rem;
}

.telephony-active-call__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
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

.telephony-floating-call {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: min(420px, calc(100vw - 32px));
  padding: 12px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: var(--app-surface);
  box-shadow: 0 14px 36px rgba(0, 0, 0, 0.32);
}

.telephony-floating-call__body {
  min-width: 160px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

@media (max-width: 900px) {
  .telephony-workspace {
    grid-template-columns: 1fr;
  }

  .telephony-dialer__actions {
    grid-template-columns: 1fr;
  }

  .telephony-floating-call {
    right: 12px;
    bottom: 12px;
    left: 12px;
    max-width: none;
  }
}
</style>
