<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NCard, NEmpty, NInput, NInputNumber, NModal, NSelect, NSpin, NTabPane, NTabs, NTag, useDialog, useMessage } from 'naive-ui'
import { http } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'
import BotSettings from './BotSettings.vue'
import VpnRequests from './VpnRequests.vue'
import VpnPeriodPicker from '@/features/vpn/VpnPeriodPicker.vue'
import VpnDeviceLimitEditor from '@/features/vpn/VpnDeviceLimitEditor.vue'
import VpnSubscriptionActions from '@/features/vpn/VpnSubscriptionActions.vue'
import VpnConnections from '@/features/vpn/VpnConnections.vue'
import type { ConnectionSlot, IssuanceEligibility } from '@/features/vpn/device-limit'
import { subscriptionKindLabels, validPeriod } from '@/features/vpn/period'

interface Node {
  id: string; name: string; host: string; status: string; vpn_ready: boolean
  cpu_percent?: number; memory_percent?: number; disk_percent?: number
  network_rx_mbps?: number; network_tx_mbps?: number; capacity_mbps?: number
  eligible_for_new_users: boolean; placement_block_reasons: string[]; drained?: boolean
}
interface Subscription {
  device_limit: number; occupied_slots: number; connections: ConnectionSlot[]
  id: string; contact_id: number; contact_name: string; kind: string; status: string
  telegram_username?: string; source_bot_name?: string; created_by: number
  expires_at: number; ready_nodes: number; total_nodes: number; enabled: boolean
  subscription_url: string; happ_url: string; clash_url: string; raw_url: string; guide_url: string; v2rayng_url: string
  upload_bytes: number; download_bytes: number; recommended_nodes: string[]
  delivery: { node_id: string; status: string }[]
  online: { node_id: string; last_online: number; hy_online: number; checked_at: number }[]
  usage_by_node: { node_id: string; metric: string; total: number }[]
  events?: { id: number; action: string; actor_id: number; actor_name?: string; at: number }[]
}
interface Contact { id: number; full_name: string; telegram_username?: string }
interface Bot { bot_id: number; bot_name: string }
const auth = useAuthStore(), route = useRoute(), router = useRouter(), message = useMessage()
const createVisible = ref(false), renewalTarget = ref<Subscription | null>(null), renewalDays = ref<number | null>(30)
const dialog = useDialog(), activeTab = ref(String(route.query.tab || (auth.isAdmin ? 'subscriptions' : 'requests'))), statusFilter = ref<string | null>(null), query = ref('')
const visibleSubscriptions = computed(() => subscriptions.value.filter(value => (!statusFilter.value || value.status === statusFilter.value) && (!query.value || `${value.contact_name} ${value.telegram_username || ''} ${value.source_bot_name || ''}`.toLowerCase().includes(query.value.toLowerCase()))))
const nodes = ref<Node[]>([]), subscriptions = ref<Subscription[]>([]), loading = ref(false)
const selectedContact = ref<number | null>(Number(route.query.contact_id) || null)
const contacts = ref<{ label: string; value: number }[]>([]), bots = ref<Bot[]>([])
const selectedBot = ref<number | null>(null), days = ref<number | null>(30), creating = ref(false)
const kind = ref<'gift' | 'purchase' | 'trial'>('gift'), detail = ref<Subscription | null>(null)
const eligibility = ref<IssuanceEligibility | null>(null)
const requestCount = ref(0)
const stale = ref(true), botUsername = ref(''), error = ref(''), pendingAction = ref('')
const editNode = ref<Node | null>(null), capacity = ref<number | null>(null), savingNode = ref(false)
let timer: ReturnType<typeof setInterval> | undefined, searchSequence = 0
const kindOptions = computed(() => [{ label: 'Подарок от менеджера', value: 'gift' }, { label: 'Покупка (оплата подтверждена менеджером)', value: 'purchase' }, ...(eligibility.value?.trial_available ? [{ label: 'Пробный период', value: 'trial' }] : [])])
const labels: Record<string, string> = { active: 'Активна', provisioning: 'Настраивается', expired: 'Истекла', revoked: 'Отключена' }
const eventLabels: Record<string, string> = { trial: 'Выдан пробный период', gift: 'Выдан подарок', purchase: 'Оформлена покупка', renew: 'Продлена подписка', revoke: 'Отключён доступ', resume: 'Включён доступ', rotate_link: 'Заменена ссылка', delete: 'Удалена подписка', set_device_limit: 'Изменён лимит подключений' }
const reasons: Record<string, string> = { high_cpu: 'Высокая загрузка CPU', high_memory: 'Мало свободной памяти', high_network: 'Загружен канал', disk_full: 'Заполнен диск', high_cpu_steal: 'Загрузка хоста провайдера', warming_up: 'Сбор первого замера', telemetry_unavailable: 'Нет связи', stale_telemetry: 'Устарели метрики', vpn_service_unavailable: 'VPN-сервис недоступен' }
const date = (value: number) => new Date(value * 1000).toLocaleString('ru-RU')
const gb = (value: number) => (value / 1024 ** 3).toFixed(2) + ' ГБ'
const number = (value?: number) => value == null ? '—' : value.toFixed(1)
const failure = (e: unknown) => e instanceof Error ? e.message : 'Не удалось выполнить операцию'

async function searchContacts(query: string) {
  const sequence = ++searchSequence
  try {
    const { data } = await http.get<{ items: Contact[] }>('/contacts', { params: { q: query || undefined, limit: 30 } })
    if (sequence === searchSequence) contacts.value = data.items.map(contact => ({ label: `${contact.full_name}${contact.telegram_username ? ' · @' + contact.telegram_username : ''} · #${contact.id}`, value: contact.id }))
  } catch (e) { message.error(failure(e)) }
}
async function contactChanged() {
  eligibility.value = null
  bots.value = []; selectedBot.value = null
  if (selectedContact.value) {
    try {
      const { data } = await http.get<{ full_name: string; linked_bots: Bot[] }>(`/contacts/${selectedContact.value}`)
      bots.value = data.linked_bots
      if (!contacts.value.some(contact => contact.value === selectedContact.value)) contacts.value.unshift({ label: data.full_name, value: selectedContact.value })
      if (bots.value.length === 1) selectedBot.value = bots.value[0].bot_id
    } catch (e) { message.error(failure(e)); selectedContact.value = null }
  }
  await refresh()
}
async function refresh() {
  loading.value = true
  try {
    const { data } = await http.get<{ nodes: Node[]; stale: boolean; bot_username: string }>('/vpn/fleet')
    nodes.value = data.nodes; stale.value = data.stale; botUsername.value = data.bot_username
    if (selectedContact.value || auth.isAdmin) {
      const response = await http.get<{ items: Subscription[]; eligibility: IssuanceEligibility | null }>('/vpn/subscriptions', { params: selectedContact.value ? { contact_id: selectedContact.value } : {} })
      subscriptions.value = response.data.items
      eligibility.value = response.data.eligibility
      if (!eligibility.value?.trial_available && kind.value === 'trial') kind.value = 'gift'
      if (detail.value) detail.value = (await http.get<Subscription>(`/vpn/subscriptions/${detail.value.id}`)).data
    } else subscriptions.value = []
    requestCount.value = (await http.get<{ open: number }>('/vpn/bot/requests/count')).data.open
    error.value = ''
  } catch (e) { error.value = failure(e) }
  finally { loading.value = false }
}
async function create() {
  if (!selectedContact.value || !validPeriod(days.value) || creating.value || !eligibility.value?.can_create || (kind.value === 'trial' && !eligibility.value.trial_available)) return
  creating.value = true
  try {
    await http.post('/vpn/subscriptions', { contact_id: selectedContact.value, days: days.value, kind: kind.value, source_bot_id: selectedBot.value })
    message.success('Подписка создана'); createVisible.value = false; await refresh()
  } catch (e) { message.error(failure(e)) }
  finally { creating.value = false }
}
async function action(value: Subscription, action: string, period: number | null = days.value) {
  pendingAction.value = value.id
  try {
    await http.post(`/vpn/subscriptions/${value.id}/action`, { action, days: action === 'renew' ? period : undefined })
    message.success(action === 'revoke' ? 'Отключение отправлено на все серверы' : 'Изменение сохранено'); await refresh()
  } catch (e) { message.error(failure(e)) }
  finally { pendingAction.value = '' }
}
function deleteSubscription(value: Subscription) {
  dialog.warning({ title: 'Удалить подписку?', content: `Контакт: ${value.contact_name}. Подписка исчезнет из списка, подключение будет отключено. История действий сохранится.`, positiveText: 'Удалить', negativeText: 'Отмена',
    onPositiveClick: async () => { await action(value, 'delete'); if (detail.value?.id === value.id) detail.value = null } })
}
async function copy(value: string) {
  try { await navigator.clipboard.writeText(value); message.success('Ссылка скопирована') }
  catch { message.error('Не удалось скопировать. Откройте детали и скопируйте ссылку вручную.') }
}
async function saveNode(drained: boolean) {
  if (!editNode.value) return
  savingNode.value = true
  try {
    await http.post(`/vpn/nodes/${editNode.value.id}`, { drained, capacity_mbps: capacity.value })
    editNode.value = null; await refresh(); message.success('Настройки сервера сохранены')
  } catch (e) { message.error(failure(e)) }
  finally { savingNode.value = false }
}
async function showDetail(value: Subscription) {
  try { detail.value = (await http.get<Subscription>(`/vpn/subscriptions/${value.id}`)).data }
  catch (e) { message.error(failure(e)) }
}
function nodeTraffic(value: Subscription, node: string) {
  return gb(value.usage_by_node.filter(item => item.node_id === node).reduce((total, item) => total + item.total, 0))
}
watch(() => route.query.tab, value => { if (typeof value === 'string') activeTab.value = value })
watch(selectedContact, contactChanged)
watch(kind, value => { days.value = value === 'trial' ? 3 : 30 })
watch(() => route.query.contact_id, value => { selectedContact.value = Number(value) || null })
onMounted(async () => { await contactChanged(); if (!selectedContact.value) await searchContacts(''); timer = setInterval(refresh, 30_000) })
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<template>
  <main class="vpn-page">
    <header class="toolbar"><div><h1>VPN</h1><p>Подписки, подключения и управление</p></div><div class="actions"><NButton :loading="loading" @click="refresh">Обновить</NButton><NButton v-if="!selectedContact || eligibility?.can_create" type="primary" @click="createVisible = true">Новая подписка</NButton></div></header>
    <NAlert v-if="error" type="error">{{ error }}</NAlert>

    <NTabs v-model:value="activeTab" type="line" animated>
      <NTabPane name="requests" :tab="`Заявки${requestCount ? ' · ' + requestCount : ''}`"><VpnRequests @count="value => requestCount = value" /></NTabPane>
      <NTabPane name="subscriptions" tab="Подписки">
        <div class="filters">
          <NSelect v-model:value="selectedContact" :options="contacts" filterable remote clearable placeholder="Контакт" @search="searchContacts" />
          <NInput v-model:value="query" clearable placeholder="Поиск в подписках" />
          <NSelect v-model:value="statusFilter" clearable placeholder="Все статусы" :options="Object.entries(labels).map(([value, label]) => ({ value, label }))" />
        </div>



    <section><h2>{{ selectedContact ? 'Подписки контакта' : 'Подписки' }} <small>{{ visibleSubscriptions.length }}</small></h2><p v-if="!selectedContact && !auth.isAdmin" class="muted">Выберите контакт, чтобы увидеть его подписки.</p>
      <NSpin :show="loading && !subscriptions.length"><div class="subscriptions">
        <NCard v-for="value in visibleSubscriptions" :key="value.id" size="small">
          <div class="toolbar"><NButton text @click="router.push({ name: 'contact-detail', params: { id: value.contact_id } })">{{ value.contact_name }}</NButton><NTag :type="value.status === 'active' ? 'success' : 'warning'">{{ labels[value.status] }}</NTag></div>
          <p>{{ subscriptionKindLabels[value.kind] || 'Подписка' }} · {{ value.source_bot_name || 'Менеджер CRM' }}<span v-if="value.telegram_username"> · @{{ value.telegram_username }}</span></p>
          <div class="subscription-summary"><span>До {{ new Date(value.expires_at * 1000).toLocaleDateString('ru-RU') }}</span><span>{{ value.occupied_slots }} / {{ value.device_limit }} подключений</span><span>{{ gb(value.upload_bytes + value.download_bytes) }}</span></div>
          <VpnSubscriptionActions :subscription="value" :can-manage="!!auth.user?.permissions?.includes('contacts.update')" show-manage :busy="pendingAction === value.id" @copy="copy" @manage="showDetail(value)" @renew="renewalTarget = value; renewalDays = 30" @action="name => name === 'delete' ? deleteSubscription(value) : action(value, name)" />
        </NCard>
      </div><NEmpty v-if="!loading && !visibleSubscriptions.length && (selectedContact || auth.isAdmin)" description="Подписки не найдены" /></NSpin>
    </section>
      </NTabPane>
      <NTabPane name="servers" tab="Серверы">
        <NAlert v-if="stale" type="warning">Нет свежих данных о состоянии серверов.</NAlert>
    <section class="fleet">
      <NCard v-for="node in nodes" :key="node.id" :title="node.name" size="small">
        <NTag :type="node.eligible_for_new_users ? 'success' : 'warning'" size="small">{{ node.eligible_for_new_users ? 'Доступен' : 'Исключён из AUTO' }}</NTag>
        <p class="muted">{{ node.host }}</p><dl><dt>CPU</dt><dd>{{ number(node.cpu_percent) }}%</dd><dt>Память</dt><dd>{{ number(node.memory_percent) }}%</dd><dt>Диск</dt><dd>{{ number(node.disk_percent) }}%</dd><dt>Сеть ↓ / ↑</dt><dd>{{ number(node.network_rx_mbps) }} / {{ number(node.network_tx_mbps) }} Мбит/с</dd></dl>
        <p v-for="reason in node.placement_block_reasons" :key="reason" class="warning">{{ reasons[reason] || reason }}</p>
        <NButton v-if="auth.isAdmin" size="small" @click="editNode = node; capacity = node.capacity_mbps ?? null">Настройки нагрузки</NButton>
      </NCard>
    </section>
      </NTabPane>
      <NTabPane v-if="auth.isAdmin" name="settings" tab="Настройки бота">
        <BotSettings @changed="refresh" />
      </NTabPane>
    </NTabs>
    <NModal v-model:show="createVisible" preset="card" title="Новая VPN-подписка" style="width: min(760px, 95vw)">
    <NCard title="Выдать VPN контакту">
      <div class="create-form">
        <NSelect v-model:value="selectedContact" :options="contacts" filterable remote clearable placeholder="Найти контакт по имени или Telegram" @search="searchContacts" />
        <NSelect v-model:value="kind" :options="kindOptions" :disabled="!eligibility?.can_create" />
        <NSelect v-model:value="selectedBot" :options="bots.map(bot => ({ label: bot.bot_name, value: bot.bot_id }))" clearable placeholder="Бот, через который оформлена подписка" />
        <VpnPeriodPicker v-model="days" :trial="kind === 'trial'" :disabled="creating" />
        <NButton type="primary" :disabled="!selectedContact || !validPeriod(days) || !eligibility?.can_create" :loading="creating" @click="create">{{ kind === 'trial' ? 'Выдать пробный VPN' : kind === 'gift' ? 'Подарить VPN' : 'Выдать подписку' }}</NButton>
      </div>
      <NAlert v-if="eligibility && !eligibility.can_create" type="info" style="margin-top: 12px">У контакта уже есть подписка. Продлите её или измените лимит подключений в её карточке.</NAlert>
      <p v-if="eligibility?.trial_used" class="muted">Пробный период уже использован.</p>
      <p class="muted">Telegram берётся из карточки контакта. В кабинете пользователь видит только свои подписки. Источник покупки сохраняется в истории.</p>
    </NCard>
    </NModal>
    <NModal :show="!!renewalTarget" preset="card" title="Продлить подписку" style="width: min(440px, 95vw)" @update:show="value => { if (!value) renewalTarget = null }">
      <p>{{ renewalTarget?.contact_name }}</p>
      <VpnPeriodPicker v-model="renewalDays" :expires-at="renewalTarget?.expires_at" :disabled="!!pendingAction" />
      <NButton style="margin-top: 16px" type="primary" :disabled="!validPeriod(renewalDays)" :loading="!!pendingAction" @click="async () => { if (renewalTarget && validPeriod(renewalDays)) { await action(renewalTarget, 'renew', renewalDays); renewalTarget = null } }">Продлить</NButton>
    </NModal>
    <NModal :show="!!detail" preset="card" title="Подписка VPN" style="width: min(800px, 95vw)" @update:show="value => { if (!value) detail = null }">
      <template v-if="detail"><p>{{ detail.contact_name }} · {{ labels[detail.status] }} · до {{ date(detail.expires_at) }}</p>
        <VpnConnections :occupied-slots="detail.occupied_slots" :device-limit="detail.device_limit" :connections="detail.connections" />
        <VpnDeviceLimitEditor v-if="auth.user?.permissions?.includes('contacts.update')" :subscription-id="detail.id" :device-limit="detail.device_limit" @saved="refresh" />
        <p class="link-text">{{ detail.subscription_url }}</p><div class="actions"><NButton @click="copy(detail.subscription_url)">Копировать</NButton><NButton @click="action(detail, 'rotate_link')">Заменить ссылку подписки</NButton></div>
        <p class="muted">Замена ссылки закрывает старый URL. Для отключения VPN на устройствах используйте «Отключить».</p>
        <table><thead><tr><th>Сервер</th><th>Выдача</th><th>Трафик</th><th>Последняя активность</th></tr></thead><tbody><tr v-for="delivery in detail.delivery" :key="delivery.node_id"><td>{{ nodes.find(node => node.id === delivery.node_id)?.name || delivery.node_id }}</td><td>{{ delivery.status === 'synced' ? 'Синхронизирован' : 'Ожидает повтора' }}</td><td>{{ nodeTraffic(detail, delivery.node_id) }}</td><td>{{ detail.online.find(item => item.node_id === delivery.node_id)?.last_online ? date(detail.online.find(item => item.node_id === delivery.node_id)!.last_online) : '—' }}</td></tr></tbody></table>
        <h3>История</h3><p v-for="event in detail.events" :key="event.id">{{ date(event.at) }} · {{ eventLabels[event.action] || event.action }} · {{ event.actor_name || 'Сотрудник' }}</p>
      </template>
    </NModal>
    <NModal :show="!!editNode" preset="card" title="Настройки нагрузки" style="width: min(480px, 95vw)" @update:show="value => { if (!value) editNode = null }">
      <p>{{ editNode?.name }}</p><label>Лимит канала провайдера, Мбит/с<NInputNumber v-model:value="capacity" :min="1" :max="100000" clearable placeholder="Не указан" /></label>
      <p class="muted">Укажите подтверждённый лимит тарифа. При загрузке канала от 85% сервер исключается из автоматического выбора.</p>
      <div class="actions"><NButton :loading="savingNode" @click="saveNode(!!editNode?.drained)">Сохранить</NButton><NButton type="warning" :loading="savingNode" @click="saveNode(!editNode?.drained)">{{ editNode?.drained ? 'Вернуть в AUTO' : 'Исключить из AUTO' }}</NButton></div>
    </NModal>
  </main>
</template>

<style scoped>
.vpn-page{padding:24px;display:grid;gap:20px}.toolbar,.summary,.actions{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}h1,h2,p{margin:0 0 10px}h1{font-size:28px}.muted{color:#7b8495;font-size:13px;margin-top:10px}.fleet{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}dl{display:grid;grid-template-columns:1fr auto;gap:6px;font-size:13px}dd{margin:0}.warning{color:#b78103;font-size:12px}.create-form{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:end}.filters{display:grid;grid-template-columns:1.5fr 1.5fr 1fr;gap:12px;margin:8px 0 20px}.subscriptions{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,360px),1fr));gap:12px}.subscription-summary{display:flex;flex-wrap:wrap;gap:8px 14px;margin:10px 0 14px;color:var(--app-text-muted);font-size:12px}.subscriptions .toolbar :deep(.n-button){min-width:0;white-space:normal;text-align:left}.subscriptions p{font-size:12px;overflow-wrap:anywhere}.actions{justify-content:flex-start}.link-text{overflow-wrap:anywhere;padding:12px;background:rgba(120,130,150,.1)}table{width:100%;border-collapse:collapse;margin-top:20px;font-size:13px}td,th{text-align:left;padding:8px;border-bottom:1px solid rgba(120,130,150,.2)}@media(max-width:1100px){.create-form{grid-template-columns:1fr 1fr}}@media(max-width:600px){.vpn-page{padding:12px}.create-form,.filters{grid-template-columns:1fr}}
</style>
