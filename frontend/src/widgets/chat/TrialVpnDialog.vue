<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NAlert, NButton, NModal, useMessage } from 'naive-ui'
import { http } from '@/shared/api/http'
import { sendMessage } from '@/features/chats/api'
import VpnPeriodPicker from '@/features/vpn/VpnPeriodPicker.vue'
import { validPeriod, vpnDeliveryText } from '@/features/vpn/period'

const props = defineProps<{ show: boolean; contactId: number; botId?: number | null; chatId?: number }>()
const emit = defineEmits<{ 'update:show': [value: boolean]; created: [] }>()
type Subscription = Parameters<typeof vpnDeliveryText>[0]
const message = useMessage(), days = ref<number | null>(3), busy = ref(false), error = ref('')
const created = ref<Subscription | null>(null), requestKey = ref(crypto.randomUUID()), deliveryKey = ref(crypto.randomUUID())
const submittedDays = ref<number | null>(null)
const preview = computed(() => created.value ? vpnDeliveryText(created.value) : `Вам выдан пробный VPN на ${days.value || '…'} дн.\n\nВ сообщении будут персональная ссылка, приложения и пошаговая инструкция по подключению.`)
watch(() => props.show, show => {
  if (show && !created.value && !submittedDays.value) { days.value = 3; error.value = '' }
})
async function submit() {
  if (!validPeriod(days.value) || busy.value) return
  busy.value = true; error.value = ''
  const chatId = props.chatId
  try {
    if (!created.value) {
      submittedDays.value ??= days.value
      const { data } = await http.post<Subscription>('/vpn/subscriptions', { contact_id: props.contactId, source_bot_id: props.botId ?? null, source_chat_id: chatId, kind: 'trial', days: submittedDays.value, idempotency_key: requestKey.value })
      created.value = data; emit('created')
    }
    if (chatId) await sendMessage(chatId, { text: vpnDeliveryText(created.value), idempotency_key: deliveryKey.value })
    message.success(chatId ? 'Пробный VPN выдан и отправлен в чат' : 'Пробный VPN выдан контакту')
    emit('update:show', false)
    created.value = null; submittedDays.value = null; requestKey.value = crypto.randomUUID(); deliveryKey.value = crypto.randomUUID()
  } catch (e) {
    error.value = created.value ? 'Подписка создана, но сообщение не отправлено. Нажмите «Повторить отправку» — новая подписка не создастся.' : e instanceof Error ? e.message : 'Не удалось выдать пробный VPN. Попробуйте ещё раз.'
  } finally { busy.value = false }
}
</script>

<template>
  <NModal :show="show" preset="card" :title="chatId ? 'Отправить пробный VPN' : 'Выдать пробный VPN'" style="width: min(520px, 95vw)" :mask-closable="!busy" :closable="!busy" @update:show="value => { if (!busy) emit('update:show', value) }">
    <div class="trial-form">
      <VpnPeriodPicker v-model="days" trial :disabled="busy || !!submittedDays" />
      <p class="hint">Бесплатный доступ для проверки подключения. По окончании срока VPN отключится автоматически. Подписка и история сохранятся в контакте.</p>
      <template v-if="chatId"><b>Клиент получит</b><pre>{{ preview }}</pre></template>
      <NAlert v-if="error" type="error">{{ error }}</NAlert>
      <NButton type="primary" :loading="busy" :disabled="!validPeriod(days)" @click="submit">{{ created && chatId ? 'Повторить отправку' : chatId ? `Выдать на ${days || '…'} дн. и отправить` : `Выдать на ${days || '…'} дн.` }}</NButton>
    </div>
  </NModal>
</template>

<style scoped>
.trial-form{display:grid;gap:16px}.hint{margin:0;color:var(--text-secondary,#8a93a3);font-size:13px}pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;font-size:13px;padding:14px;border-radius:10px;background:rgba(120,130,150,.1)}
</style>
