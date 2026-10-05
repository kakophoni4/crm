<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NInputNumber, NSelect, NSpin, NTag, useDialog, useMessage } from 'naive-ui'
import { useRouter } from 'vue-router'
import { http } from '@/shared/api/http'
import { sendMessage } from '@/features/chats/api'

const props = defineProps<{ contactId: number; botId?: number | null; chatId?: number }>()
interface Subscription { id: string; status: string; kind: string; expires_at: number; enabled: boolean; ready_nodes: number; total_nodes: number; source_bot_name?: string; happ_url: string; clash_url: string; guide_url: string; v2rayng_url: string; upload_bytes: number; download_bytes: number }
const router = useRouter(), message = useMessage(), dialog = useDialog()
const items = ref<Subscription[]>([]), days = ref<number | null>(30), loading = ref(false), busy = ref(false), error = ref('')
const kind = ref<'gift' | 'purchase'>('gift'), sourceBot = ref<number | null>(null), bots = ref<{ label: string; value: number }[]>([])
const labels: Record<string, string> = { active: 'Активна', provisioning: 'Настраивается', expired: 'Истекла', revoked: 'Отключена' }
const requests = ref<{ id: number; kind: string; state: string; created_at: number }[]>([])
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
  if (!days.value) return
  const body = { contact_id: props.contactId, days: days.value, kind: kind.value, source_bot_id: sourceBot.value, source_chat_id: props.chatId }
  dialog.warning({ title: kind.value === 'gift' ? 'Подарить VPN' : 'Оформить продажу VPN',
    content: `${body.days} дней.${body.kind === 'purchase' ? ' Подтвердите, что оплата получена. Эта кнопка не списывает деньги.' : ' Подписка будет выдана бесплатно.'}`,
    positiveText: body.kind === 'gift' ? 'Подарить' : 'Оплата получена', negativeText: 'Отмена',
    onPositiveClick: async () => {
      busy.value = true
      try { await http.post('/vpn/subscriptions', body); message.success('Подписка создана'); await refresh() }
      catch (e) { message.error(failure(e)) } finally { busy.value = false }
    } })
}
function action(value: Subscription, action: string) {
  const period = days.value
  dialog.warning({ title: action === 'delete' ? 'Удалить подписку?' : action === 'revoke' ? 'Отключить VPN?' : `Продлить на ${period} дней?`,
    content: action === 'delete' ? 'Подписка исчезнет из списка, доступ будет отключён. История действий сохранится.' : 'Изменение применяется к подписке.', positiveText: 'Подтвердить', negativeText: 'Отмена',
    onPositiveClick: async () => {
      busy.value = true
      try { await http.post(`/vpn/subscriptions/${value.id}/action`, { action, days: action === 'renew' ? period : undefined }); await refresh() }
      catch (e) { message.error(failure(e)) } finally { busy.value = false }
    } })
}
function deliver(value: Subscription) {
  const chatId = props.chatId
  if (!chatId) return
  const text = `Ваша VPN-подписка ${value.kind === 'gift' ? 'в подарок ' : ''}до ${date(value.expires_at)}.\nHapp: ${value.happ_url}\nKoala Clash: ${value.clash_url}\nv2rayNG: ${value.v2rayng_url}\nСкачать приложение и подключиться: ${value.guide_url}`
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
onUnmounted(() => { disposed = true; ++generation; ++setupSequence; if (timer) clearInterval(timer) })
</script>

<template>
  <section class="contact-vpn">
    <header><div><h3>VPN клиента</h3><span>Подписки и подключения</span></div><NButton size="small" :loading="loading" @click="refresh">Обновить</NButton></header>
    <NAlert v-if="error" type="error">{{ error }}</NAlert>
    <NCard v-for="request in requests.filter(item => item.state === 'open')" :key="request.id" size="small" :title="`Заявка из бота №${request.id}`">
      <p>{{ requestLabels[request.kind] }} · {{ date(request.created_at) }}</p>
      <NButton size="small" @click="closeRequest(request.id)">Отметить обработанной</NButton>
    </NCard>
    <NCard size="small" title="Выдать подписку">
      <div class="form">
        <NSelect v-model:value="kind" :options="[{ label: 'Подарить VPN', value: 'gift' }, { label: 'Продать VPN', value: 'purchase' }]" />
        <label>Срок, дней<NInputNumber v-model:value="days" :min="1" :max="3650" /></label>
        <NSelect v-model:value="sourceBot" :options="bots" :disabled="!!chatId" :clearable="!chatId" placeholder="Источник: бот или менеджер CRM" />
        <NButton type="primary" :loading="busy" :disabled="!days" @click="create">{{ kind === 'gift' ? 'Подарить VPN' : 'Оформить продажу' }}</NButton>
      </div>
    </NCard>
    <NSpin :show="loading && !items.length">
      <p v-if="!items.length && !loading">У контакта пока нет VPN-подписок.</p>
      <NCard v-for="item in items" :key="item.id" size="small">
        <header><b>{{ item.kind === 'gift' ? 'Подарок' : 'Покупка' }}</b><NTag :type="item.status === 'active' ? 'success' : 'warning'">{{ labels[item.status] }}</NTag></header>
        <p>До {{ date(item.expires_at) }}</p>
        <p>{{ item.source_bot_name || 'Менеджер CRM' }} · {{ ((item.upload_bytes + item.download_bytes) / 1024 ** 3).toFixed(2) }} ГБ</p>
        <div class="actions"><NButton size="small" :disabled="item.status !== 'active'" @click="copy(item.happ_url)">Happ</NButton><NButton size="small" :disabled="item.status !== 'active'" @click="copy(item.clash_url)">Koala Clash</NButton><NButton size="small" :disabled="item.status !== 'active'" @click="copy(item.v2rayng_url)">v2rayNG</NButton><NButton size="small" :disabled="item.status !== 'active'" @click="copy(item.guide_url)">Инструкция и APK</NButton><NButton v-if="chatId" size="small" type="primary" secondary :disabled="item.status !== 'active' || busy" @click="deliver(item)">Отправить в чат</NButton><NButton size="small" :disabled="busy || !days" @click="action(item, 'renew')">Продлить</NButton><NButton v-if="item.enabled" size="small" type="error" secondary :disabled="busy" @click="action(item, 'revoke')">Отключить</NButton><NButton size="small" quaternary type="error" :disabled="busy" @click="action(item, 'delete')">Удалить</NButton></div>
      </NCard>
    </NSpin>
    <NButton text @click="router.push({ name: 'vpn', query: { contact_id: contactId } })">Открыть историю и управление VPN →</NButton>
  </section>
</template>

<style scoped>
.contact-vpn { display: grid; gap: 14px; padding: 16px; min-width: 0; overflow: auto; }
header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
h3 { margin: 0 0 4px; } header span, p { color: var(--text-secondary, #8a93a3); font-size: 13px; }
.form { display: grid; gap: 12px; } .actions { display: flex; flex-wrap: wrap; gap: 8px; }
.n-card + .n-card { margin-top: 12px; }
</style>
