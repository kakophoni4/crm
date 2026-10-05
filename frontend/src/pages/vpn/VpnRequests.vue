<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NAlert, NButton, NCard, NCheckbox, NEmpty, NInput, NModal, NSelect, NSpin, NTag, useDialog, useMessage } from 'naive-ui'
import { http } from '@/shared/api/http'
import VpnPeriodPicker from '@/features/vpn/VpnPeriodPicker.vue'
import { validPeriod } from '@/features/vpn/period'

interface Request { id: number; contact_id: number | null; contact_name?: string; telegram_username?: string; user_id?: number; subscription_id?: string; kind: string; state: string; created_at: number }
const router = useRouter(), dialog = useDialog(), message = useMessage()
const emit = defineEmits<{ count: [value: number] }>()
const items = ref<Request[]>([]), loading = ref(false), error = ref(''), search = ref('')
const state = ref<string | null>('open'), renewal = ref<Request | null>(null), days = ref<number | null>(30), confirmed = ref(false), busy = ref(false)
const renewalExpiresAt = ref<number | undefined>()
const labels: Record<string, string> = { renew: 'Продление VPN', buy: 'Покупка VPN', support: 'Помощь с подключением' }
const statuses: Record<string, string> = { open: 'Ожидает обработки', done: 'Обработана', dismissed: 'Отклонена' }
const visible = computed(() => items.value.filter(item => !search.value || `${item.contact_name || ''} ${item.telegram_username || ''} ${labels[item.kind] || ''}`.toLowerCase().includes(search.value.toLowerCase())))
const date = (value: number) => new Date(value * 1000).toLocaleString('ru-RU')
let timer: ReturnType<typeof setInterval> | undefined, generation = 0, disposed = false
async function refresh() {
  const request = ++generation
  loading.value = true
  try {
    const [list, count] = await Promise.all([
      http.get<{ items: Request[] }>('/vpn/bot/requests', { params: state.value ? { state: state.value } : {} }),
      http.get<{ open: number }>('/vpn/bot/requests/count'),
    ])
    if (disposed || request !== generation) return
    items.value = list.data.items; error.value = ''
    emit('count', count.data.open)
    window.dispatchEvent(new Event('vpn-requests-changed'))
  } catch { if (!disposed && request === generation) error.value = 'Не удалось загрузить заявки. Попробуйте обновить список.' }
  finally { if (!disposed && request === generation) loading.value = false }
}
function close(item: Request, result: 'done' | 'dismissed') {
  dialog.warning({ title: result === 'done' ? 'Отметить заявку обработанной?' : 'Отклонить заявку?', content: result === 'done' ? 'Это закроет обращение. Для добавления срока подписке используйте кнопку «Продлить».' : 'Заявка будет закрыта без изменения подписки.', positiveText: 'Подтвердить', negativeText: 'Отмена',
    onPositiveClick: async () => {
      try { await http.post(`/vpn/bot/requests/${item.id}`, { state: result }); await refresh() }
      catch { message.error('Не удалось обновить заявку') }
    } })
}
async function renew() {
  if (!renewal.value || !validPeriod(days.value) || !confirmed.value || busy.value) return
  busy.value = true
  try {
    const { data } = await http.post<{ already_processed: boolean }>(`/vpn/bot/requests/${renewal.value.id}/renew`, { days: days.value })
    message.success(data.already_processed ? 'Заявка уже обработана. Повторное продление не выполнено.' : 'Подписка продлена, заявка обработана')
    renewal.value = null; await refresh()
  } catch { message.error('Продление не выполнено. Обновите список и проверьте подписку.') }
  finally { busy.value = false }
}
async function openRenewal(item: Request) {
  renewal.value = item; days.value = 30; confirmed.value = false; renewalExpiresAt.value = undefined
  try {
    const { data } = await http.get<{ expires_at: number }>(`/vpn/subscriptions/${item.subscription_id}`)
    if (renewal.value?.id === item.id) renewalExpiresAt.value = data.expires_at
  } catch { message.error('Не удалось уточнить текущий срок подписки') }
}
watch(state, refresh)
onMounted(() => { void refresh(); timer = setInterval(() => { void refresh() }, 30_000) })
onUnmounted(() => { disposed = true; ++generation; if (timer) clearInterval(timer) })
</script>

<template>
  <section class="request-list">
    <div class="toolbar"><div><h2>Заявки на VPN</h2><p class="muted">Продления, покупки и помощь — без открытия чата.</p></div><NButton :loading="loading" @click="refresh">Обновить заявки</NButton></div>
    <div class="filters"><NInput v-model:value="search" clearable placeholder="Поиск по контакту, нику или типу заявки" /><NSelect v-model:value="state" :options="[{ label: 'Открытые', value: 'open' }, { label: 'Обработанные', value: 'done' }, { label: 'Отклонённые', value: 'dismissed' }]" /></div>
    <NAlert v-if="error" type="error">{{ error }}</NAlert>
    <NSpin :show="loading && !items.length">
      <div class="cards"><NCard v-for="item in visible" :key="item.id" size="small">
        <div class="toolbar"><strong>{{ labels[item.kind] || item.kind }}</strong><NTag :type="item.state === 'open' ? 'error' : 'default'">{{ statuses[item.state] || item.state }}</NTag></div>
        <p class="contact"><NButton v-if="item.contact_id" text type="primary" @click="router.push({ name: 'contact-detail', params: { id: item.contact_id } })">{{ item.contact_name || 'Открыть контакт' }}</NButton><span v-else>Контакт ещё не привязан</span><span v-if="item.telegram_username"> · @{{ item.telegram_username }}</span><span v-else-if="!item.contact_id && item.user_id"> · Telegram ID {{ item.user_id }}</span></p>
        <p class="muted">{{ date(item.created_at) }} · Заявка №{{ item.id }}</p>
        <div v-if="item.state === 'open'" class="actions"><NButton v-if="item.kind === 'renew' && item.subscription_id && item.contact_id" type="primary" @click="openRenewal(item)">Продлить</NButton><NButton v-if="item.contact_id" @click="router.push({ name: 'vpn', query: { contact_id: item.contact_id, tab: 'subscriptions' } })">Подписки контакта</NButton><NButton @click="close(item, 'done')">Обработана</NButton><NButton quaternary type="error" @click="close(item, 'dismissed')">Отклонить</NButton></div>
      </NCard></div>
      <NEmpty v-if="!loading && !error && !visible.length" description="Заявок не найдено" />
    </NSpin>
    <NModal :show="!!renewal" preset="card" title="Продлить VPN по заявке" style="width: min(480px, 95vw)" :mask-closable="!busy" @update:show="value => { if (!value && !busy) renewal = null }">
      <p>{{ renewal?.contact_name }}<span v-if="renewal?.telegram_username"> · @{{ renewal.telegram_username }}</span></p>
      <VpnPeriodPicker v-model="days" :expires-at="renewalExpiresAt" :disabled="busy" />
      <p class="muted">Срок будет добавлен к подписке. Если она истекла — отсчёт начнётся с текущего времени. Заявка будет отмечена обработанной.</p>
      <NCheckbox v-model:checked="confirmed">Оплата получена или бесплатное продление согласовано</NCheckbox>
      <NButton style="margin-top: 18px" type="primary" :loading="busy" :disabled="!confirmed || !validPeriod(days)" @click="renew">Продлить на {{ days || '…' }} дн. и обработать</NButton>
    </NModal>
  </section>
</template>

<style scoped>
.request-list{display:grid;gap:18px}.toolbar,.actions{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}.filters{display:grid;grid-template-columns:1fr 230px;gap:12px}.cards{display:grid;gap:12px}.actions{justify-content:flex-start}h2,p{margin:0 0 8px}.contact{margin-top:12px}.muted{color:#7b8495;font-size:13px} @media(max-width:600px){.filters{grid-template-columns:1fr}}
</style>
