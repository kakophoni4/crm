<script setup lang="ts">
import { Delete, Phone, PhoneCall, PhoneOff, Unplug, Wifi } from 'lucide-vue-next'
import { NButton, NIcon, NSelect, NSpin, NTag, useMessage } from 'naive-ui'
import type { SelectOption } from 'naive-ui'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import {
  getTelephonyWebrtcConfig,
  listTelephonyAccounts,
  type TelephonyAccount,
  type TelephonyWebrtcConfig,
} from '@/features/telephony/api'
import { CrmSoftphone, type SoftphoneStatus } from '@/features/telephony/softphone'
import { AppError } from '@/shared/api/http'

const message = useMessage()
const loading = ref(false)
const connecting = ref(false)
const calling = ref(false)
const accounts = ref<TelephonyAccount[]>([])
const selectedAccountId = ref<number | null>(null)
const dialNumber = ref('')
const webrtcConfig = ref<TelephonyWebrtcConfig | null>(null)
const status = ref<SoftphoneStatus>('idle')
const remoteAudio = ref<HTMLAudioElement | null>(null)

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

const dialKeys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '+', '0', '#']

function appendDigit(value: string): void {
  dialNumber.value = `${dialNumber.value}${value}`
}

function backspace(): void {
  dialNumber.value = dialNumber.value.slice(0, -1)
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
    webrtcConfig.value = config
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
  calling.value = true
  try {
    await softphone.call(dialNumber.value)
  } catch (err) {
    status.value = 'registered'
    message.error(err instanceof Error ? err.message : 'Не удалось начать звонок')
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

onMounted(() => {
  void load()
})

onBeforeUnmount(() => {
  void softphone.disconnect()
})
</script>

<template>
  <section class="telephony-page">
    <header class="telephony-page__header">
      <div>
        <h1 class="telephony-page__title">Телефония</h1>
        <p class="telephony-page__hint">Звонки через внутренний WebRTC extension и Bitcall trunk.</p>
      </div>
      <NTag :type="status === 'registered' || status === 'in-call' ? 'success' : 'default'">
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
        </section>

        <section class="telephony-status" aria-label="Telephony status">
          <div class="telephony-status__icon">
            <NIcon :size="28"><Phone /></NIcon>
          </div>
          <h2>WebRTC bridge</h2>
          <p>
            Браузер регистрируется во внутреннем Asterisk по SIP over WebSocket. Bitcall SIP
            credentials остаются на серверной стороне и не отдаются в JavaScript.
          </p>
          <dl v-if="selectedAccount" class="telephony-status__meta">
            <dt>Provider</dt>
            <dd>{{ selectedAccount.provider }}</dd>
            <dt>SIP host</dt>
            <dd>{{ selectedAccount.sip_host }}:{{ selectedAccount.sip_port }}</dd>
            <dt>WebRTC WS</dt>
            <dd>{{ selectedAccount.webrtc_ws_url || 'ws://127.0.0.1:8088/ws' }}</dd>
            <dt>Extension</dt>
            <dd>{{ webrtcConfig?.extension || 'не выдан' }}</dd>
          </dl>
          <div v-else class="telephony-status__empty">
            <NIcon><Unplug /></NIcon>
            <span>Нет активных SIP-аккаунтов</span>
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
.telephony-status {
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

.telephony-status {
  min-height: 320px;
}

.telephony-status__icon {
  width: 52px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--app-primary);
  background: color-mix(in srgb, var(--app-primary) 12%, transparent);
}

.telephony-status h2 {
  margin: 16px 0 8px;
  font-size: 1.125rem;
}

.telephony-status p {
  max-width: 620px;
  margin: 0;
  color: var(--app-text-muted);
  line-height: 1.55;
}

.telephony-status__meta {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 8px 12px;
  margin: 20px 0 0;
}

.telephony-status__meta dt {
  color: var(--app-text-muted);
}

.telephony-status__meta dd {
  margin: 0;
  min-width: 0;
  word-break: break-word;
}

.telephony-status__empty {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 20px;
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
