<script setup lang="ts">
import { ref } from 'vue'
import { NAlert, NButton, NCard, NInput, NModal, useMessage } from 'naive-ui'
import { http } from '@/shared/api/http'
const emit = defineEmits<{ changed: [] }>()
const message = useMessage(), open = ref(false), token = ref(''), confirmation = ref(''), busy = ref(false)
const pending = ref<{ challenge: string; username: string } | null>(null)
const delivery = ref<Record<string, number>>({})
async function refresh() {
  try {
    delivery.value = (await http.get('/vpn/bot/notifications')).data
  } catch { message.error('Не удалось загрузить статус рассылки') }
}
function reset() { token.value = ''; confirmation.value = ''; pending.value = null }
async function prepare() {
  busy.value = true
  try {
    pending.value = (await http.post('/vpn/bot/prepare', { token: token.value.trim() })).data
    token.value = ''
  } catch { message.error('Проверка не пройдена. Проверьте токен и отсутствие вебхука у бота.') }
  finally { busy.value = false }
}
async function confirm() {
  if (!pending.value || confirmation.value !== 'ЗАМЕНИТЬ БОТА') return
  busy.value = true
  try {
    await http.post('/vpn/bot/confirm', { challenge: pending.value.challenge, confirmation: confirmation.value })
    reset(); open.value = false; emit('changed'); await refresh(); message.success('Бот заменён. Рассылка поставлена в очередь.')
  } catch { reset(); message.error('Замена не выполнена. Начните проверку заново.') }
  finally { busy.value = false }
}
</script>
<template>
  <NCard size="small" title="Telegram-кабинет VPN">
    <p>Сменить токен или подключить другого бота может только администратор. Подписки привязаны к Telegram ID клиентов.</p>
    <NButton @click="reset(); open = true">Изменить токен бота</NButton>
    <NButton style="margin-left: 8px" @click="refresh">Обновить статус рассылки</NButton>
    <p v-if="Object.keys(delivery).length">Рассылка: отправлено {{ delivery.sent || 0 }} · ожидает {{ delivery.pending || 0 }} · ошибок {{ delivery.failed || 0 }}</p>
  </NCard>
  <NModal v-model:show="open" preset="card" :mask-closable="!busy" style="width: min(520px, 95vw)" title="Смена бота VPN" @after-leave="reset">
    <template v-if="!pending">
      <p>Шаг 1 из 2. Введите новый токен и подтвердите проверку бота.</p>
      <NInput v-model:value="token" type="password" show-password-on="click" autocomplete="off" placeholder="Новый токен Telegram" />
      <NButton style="margin-top: 16px" type="primary" :loading="busy" :disabled="!token.trim()" @click="prepare">Подтвердить и проверить бота</NButton>
    </template>
    <template v-else>
      <NAlert type="warning">Шаг 2 из 2. Кабинет переключится на @{{ pending.username }}. Пользователям отправится сообщение со ссылкой на бота. Для рассылки из другого старого бота его токен должен ещё работать. Проверка действует 3 минуты.</NAlert>
      <p>Для окончательной замены введите: <b>ЗАМЕНИТЬ БОТА</b></p>
      <NInput v-model:value="confirmation" placeholder="ЗАМЕНИТЬ БОТА" />
      <NButton style="margin-top: 16px" type="error" :loading="busy" :disabled="confirmation !== 'ЗАМЕНИТЬ БОТА'" @click="confirm">Окончательно заменить бота</NButton>
    </template>
  </NModal>
</template>
