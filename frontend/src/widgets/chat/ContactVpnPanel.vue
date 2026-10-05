<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NModal, NSelect, NSpin, NTag, useDialog, useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { http } from '@/shared/api/http'
import { sendMessage } from '@/features/chats/api'
import VpnPeriodPicker from '@/features/vpn/VpnPeriodPicker.vue'
import { subscriptionKindLabels, validPeriod, vpnDeliveryText } from '@/features/vpn/period'
import TrialVpnDialog from './TrialVpnDialog.vue'
import { useAuthStore } from '@/shared/store/auth'

const props = defineProps<{ contactId: number; botId?: number | null; chatId?: number }>()
interface Subscription { id: string; status: string; kind: string; expires_at: number; enabled: boolean; ready_nodes: number; total_nodes: number; source_bot_name?: string; happ_url: string; clash_url: string; guide_url: string; v2rayng_url: string; upload_bytes: number; download_bytes: number }
const router = useRouter(), message = useMessage(), dialog = useDialog()
const auth = useAuthStore()
const items = ref<Subscription[]>([]), days = ref<number | null>(30), loading = ref(false), busy = ref(false), error = ref('')
const kind = ref<'gift' | 'purchase' | 'trial'>('gift'), sourceBot = ref<number | null>(null), bots = ref<{ label: string; value: number }[]>([])
const trialVisible = ref(false), renewalTarget = ref<Subscription | null>(null), renewalDays = ref<number | null>(30)
const labels: Record<string, string> = { active: 'Активна', provisioning: 'Настраивается', expired: 'Истекла', revoked: 'Отключена' }
const requests = ref<{ id: number; kind: string; state: string; created_at: number; requested_days?: number | null }[]>([])
const requestLabels: Record<string, string> = { buy: 'Покупка VPN', renew: 'Продление VPN', support: 'Помощь с VPN' }
async function closeRequest(id: number) {
  try { await http.post(`/vpn/bot/requests/${id}`, { state: 'done' }); await refresh() }
  catch (e) { message.error(failure(e)) }
}
let generation = 0, setupSequence = 0, disposed = false, timer: ReturnType<typeof setInterval> | undefined
const date = (value: number) => new Date(value * 1000).toLocaleDateString('ru-RU')
const failure = (e: unknown) => e instanceof Error ? e.message : 'Операция не выполнена'
async function refresh() {
  const contact = props.contactId, request = ++generation
  loading.value = true
  try {
    const { data } = await http.get<{ items: Subscription[] }>('/vpn/subscriptions', { params: { contact_id: contact } })
    const response = await http.get<{ items: typeof requests.value }>('/vpn/bot/requests', { params: { contact_id: contact } })
    if (request === generation) { items.value = data.items; requests.value = response.data.items; error.value = '' }
  } catch (e) { if (request === generation) error.value = failure(e) }
  finally { if (request === generation) loading.value = false }
}
async function setup() {
  const sequence = ++setupSequence
  const contact = props.contactId
  items.value = []; bots.value = []; sourceBot.value = null
  if (timer) clearInterval(timer)
  await refresh()
  if (disposed || sequence !== setupSequence) return
  try {
    const { data } = await http.get<{ linked_bots: { bot_id: number; bot_name: string }[] }>(`/contacts/${contact}`)
    if (disposed || sequence !== setupSequence || contact !== props.contactId) return
    bots.value = data.linked_bots.map(bot => ({ label: bot.bot_name, value: bot.bot_id }))
    sourceBot.value = props.chatId ? props.botId ?? null : bots.value.length === 1 ? bots.value[0]!.value : null
  } catch (e) { if (contact === props.contactId) error.value = failure(e) }
  if (!disposed && sequence === setupSequence) timer = setInterval(refresh, 30_000)
}
function create() {
  if (!validPeriod(days.value) || busy.value) return
  const body = { contact_id: props.contactId, days: days.value, kind: kind.value, source_bot_id: sourceBot.value, source_chat_id: props.chatId }
  dialog.warning({ title: kind.value === 'trial' ? 'Выдать пробный VPN' : kind.value === 'gift' ? 'Подарить VPN' : 'Оформить продажу VPN',
    content: `${body.days} дней.${body.kind === 'purchase' ? ' Подтвердите, что оплата получена. Эта кнопка не списывает деньги.' : ' Подписка будет выдана бесплатно.'}`,
    positiveText: body.kind === 'purchase' ? 'Оплата получена' : 'Выдать', negativeText: 'Отмена',
    onPositiveClick: async () => {
      busy.value = true
      try { await http.post('/vpn/subscriptions', body); message.success('Подписка создана'); await refresh() }
      catch (e) { message.error(failure(e)) } finally { busy.value = false }
    } })
}
function action(value: Subscription, action: string) {
  dialog.warning({ title: action === 'delete' ? 'Удалить подписку?' : 'Отключить VPN?',
    content: action === 'delete' ? 'Подписка исчезнет из списка, доступ будет отключён. История действий сохранится.' : 'Изменение применяется к подписке.', positiveText: 'Подтвердить', negativeText: 'Отмена',
    onPositiveClick: async () => {
      busy.value = true
      try { await http.post(`/vpn/subscriptions/${value.id}/action`, { action }); await refresh() }
      catch (e) { message.error(failure(e)) } finally { busy.value = false }
    } })
}
async function renew() {
  if (!renewalTarget.value || !validPeriod(renewalDays.value) || busy.value) return
  busy.value = true
  try {
    await http.post(`/vpn/subscriptions/${renewalTarget.value.id}/action`, { action: 'renew', days: renewalDays.value })
    message.success('Подписка продлена'); renewalTarget.value = null; await refresh()
  } catch (e) { message.error(failure(e)) }
  finally { busy.value = false }
}
function deliver(value: Subscription) {
  const chatId = props.chatId
  if (!chatId) return
  const text = vpnDeliveryText(value)
  dialog.info({ title: 'Отправить подписку в этот чат?', content: text, positiveText: 'Отправить клиенту', negativeText: 'Отмена',
    onPositiveClick: async () => {
      busy.value = true
      try { await sendMessage(chatId, { text, idempotency_key: crypto.randomUUID() }); message.success('Ссылка отправлена в чат') }
      catch (e) { message.error(failure(e)) } finally { busy.value = false }
    } })
}
async function copy(url: string) {
  try { await navigator.clipboard.writeText(url); message.success('Ссылка скопирована') }
  catch { message.error('Не удалось скопировать ссылку') }
}
watch(() => [props.contactId, props.botId], setup, { immediate: true })
watch(kind, value => { days.value = value === 'trial' ? 3 : 30 })
onUnmounted(() => { disposed = true; ++generation; ++setupSequence; if (timer) clearInterval(timer) })
</script>

<template>
  <section class="contact-vpn">
    <header><div><h3>VPN клиента</h3><span>Подписки и подключения</span></div><NButton size="small" :loading="loading" @click="refresh">Обновить</NButton></header>
    <NAlert v-if="error" type="error">{{ error }}</NAlert>
    <NButton v-if="auth.user?.permissions?.includes('contacts.update') && (!chatId || auth.user?.permissions?.includes('chats.write'))" type="primary" secondary :disabled="busy" @click="trialVisible = true">{{ chatId ? 'Отправить пробный VPN' : 'Выдать пробный VPN' }}</NButton>
    <TrialVpnDialog :key="`${contactId}-${chatId || 0}`" v-model:show="trialVisible" :contact-id="contactId" :bot-id="chatId ? botId : sourceBot" :chat-id="chatId" @created="refresh" />
    <NCard v-for="request in requests.filter(item => item.state === 'open')" :key="request.id" size="small" :title="`Заявка из бота №${request.id}`">
      <p>{{ requestLabels[request.kind] }} · {{ date(request.created_at) }}</p>
      <p v-if="request.requested_days">Клиент выбрал {{ request.requested_days }} дн.</p>
      <NButton size="small" @click="closeRequest(request.id)">Отметить обработанной</NButton>
    </NCard>
    <NCard v-if="auth.user?.permissions?.includes('contacts.update')" size="small" title="Выдать подписку">
      <div class="form">
        <NSelect v-model:value="kind" :options="[{ label: 'Подарить VPN', value: 'gift' }, { label: 'Продать VPN', value: 'purchase' }, { label: 'Пробный период', value: 'trial' }]" />
        <VpnPeriodPicker v-model="days" :trial="kind === 'trial'" :disabled="busy" />
        <NSelect v-model:value="sourceBot" :options="bots" :disabled="!!chatId" :clearable="!chatId" placeholder="Источник: бот или менеджер CRM" />
        <NButton type="primary" :loading="busy" :disabled="!validPeriod(days)" @click="create">{{ kind === 'trial' ? 'Выдать пробный VPN' : kind === 'gift' ? 'Подарить VPN' : 'Оформить продажу' }}</NButton>
      </div>
    </NCard>
    <NSpin :show="loading && !items.length">
      <p v-if="!items.length && !loading">У контакта пока нет VPN-подписок.</p>
      <NCard v-for="item in items" :key="item.id" size="small">
        <header><b>{{ subscriptionKindLabels[item.kind] || 'Подписка' }}</b><NTag :type="item.status === 'active' ? 'success' : 'warning'">{{ labels[item.status] }}</NTag></header>
        <p>До {{ date(item.expires_at) }}</p>
        <p>{{ item.source_bot_name || 'Менеджер CRM' }} · {{ ((item.upload_bytes + item.download_bytes) / 1024 ** 3).toFixed(2) }} ГБ</p>
        <div class="actions"><NButton size="small" :disabled="item.status !== 'active'" @click="copy(item.happ_url)">Happ</NButton><NButton size="small" :disabled="item.status !== 'active'" @click="copy(item.clash_url)">Koala Clash</NButton><NButton size="small" :disabled="item.status !== 'active'" @click="copy(item.v2rayng_url)">v2rayNG</NButton><NButton size="small" :disabled="item.status !== 'active'" @click="copy(item.guide_url)">Инструкция и APK</NButton><NButton v-if="chatId" size="small" type="primary" secondary :disabled="item.status !== 'active' || busy" @click="deliver(item)">Отправить в чат</NButton><NButton size="small" :disabled="busy" @click="renewalTarget = item; renewalDays = 30">Продлить</NButton><NButton v-if="item.enabled" size="small" type="error" secondary :disabled="busy" @click="action(item, 'revoke')">Отключить</NButton><NButton size="small" quaternary type="error" :disabled="busy" @click="action(item, 'delete')">Удалить</NButton></div>
      </NCard>
    </NSpin>
    <NButton text @click="router.push({ name: 'vpn', query: { contact_id: contactId } })">Открыть историю и управление VPN →</NButton>
    <NModal :show="!!renewalTarget" preset="card" title="Продлить VPN" style="width: min(480px, 95vw)" :mask-closable="!busy" :closable="!busy" @update:show="value => { if (!value && !busy) renewalTarget = null }">
      <VpnPeriodPicker v-model="renewalDays" :expires-at="renewalTarget?.expires_at" :disabled="busy" />
      <NButton style="margin-top: 18px" type="primary" :loading="busy" :disabled="!validPeriod(renewalDays)" @click="renew">Продлить на {{ renewalDays || '…' }} дн.</NButton>
    </NModal>
  </section>
</template>

<style scoped>
.contact-vpn { display: grid; gap: 14px; padding: 16px; min-width: 0; overflow: auto; }
header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
h3 { margin: 0 0 4px; } header span, p { color: var(--text-secondary, #8a93a3); font-size: 13px; }
.form { display: grid; gap: 12px; } .actions { display: flex; flex-wrap: wrap; gap: 8px; }
.n-card + .n-card { margin-top: 12px; }
</style>
