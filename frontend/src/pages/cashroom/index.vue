<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import {
  NButton,
  NInput,
  NAutoComplete,
  NInputNumber,
  NSelect,
  NDatePicker,
  NModal,
  NPagination,
  NSpin,
  NTag,
  NEmpty,
  NAlert,
  useMessage,
  useDialog,
} from 'naive-ui'
import { Plus, ArrowDownLeft, ArrowUpRight, Wallet, RefreshCw } from 'lucide-vue-next'
import { http } from '@/shared/api/http'

type Deal = {
  id: number
  entered_on: string
  due_on: string | null
  payer: string
  receiver: string
  payer_inn: string
  receiver_inn: string
  client: string
  executor: string
  manager: string
  amount: string
  executor_rate: string
  client_rate: string
  manager_rate: string
  comment: string
  version: number
  status: string
  expected_received: string
  expected_issued: string
  received: string
  issued: string
  receivable: string
  payable: string
  revenue: string
  salary: string
  profit: string
  planned_profit: string
}
type Movement = {
  id: number
  deal_id: number | null
  account_name: string
  kind: string
  amount: string
  occurred_on: string
  client: string
  manager: string
  comment: string
  comment2: string
  voided: boolean
}
type History = {
  id: number
  action: string
  actor: string
  at: string
  changes: Record<string, unknown>
}
const message = useMessage(),
  dialog = useDialog()
const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
const money = (v: unknown) =>
  new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 2,
  }).format(Number(v ?? 0))
const date = (v: string | null) => (v ? v.split('T')[0]!.split('-').reverse().join('.') : '—')
const errorText = (e: any) =>
  e?.response?.data?.error?.message || e?.message || 'Не удалось выполнить действие'
const tab = ref('deals'),
  q = ref(''),
  state = ref('all'),
  page = ref(1),
  ledgerPage = ref(1)
const start = ref<string | null>(null),
  end = ref<string | null>(null),
  accountId = ref<number | null>(null)
const loading = ref(false),
  error = ref(''),
  saving = ref(false)
const deals = ref<Deal[]>([]),
  movements = ref<Movement[]>([]),
  movementCount = ref(0)
const accounts = ref<{ id: number; name: string; balance: string }[]>([])
const summary = ref<Record<string, string | number>>({})
const accountOptions = computed(() => accounts.value.map((a) => ({ label: a.name, value: a.id })))
const states = [
  { label: 'Все сделки', value: 'all' },
  { label: 'Ожидают', value: 'waiting' },
  { label: 'Частично', value: 'partial' },
  { label: 'Просрочены', value: 'overdue' },
  { label: 'Закрыты', value: 'closed' },
]
const kinds: Record<string, string> = {
  receive: 'Получение',
  issue: 'Выдача',
  income: 'Приход',
  expense: 'Расход',
  opening: 'Начальный остаток',
}
let loadId = 0,
  searchTimer: ReturnType<typeof setTimeout> | undefined
async function load() {
  const id = ++loadId
  loading.value = true
  error.value = ''
  try {
    const [a, d, m] = await Promise.all([
      http.get('/cashroom/accounts'),
      http.get('/cashroom/deals', {
        params: {
          q: q.value,
          state: state.value,
          page: page.value,
          start: start.value,
          end: end.value,
        },
      }),
      http.get('/cashroom/movements', {
        params: {
          account_id: accountId.value,
          page: ledgerPage.value,
          start: start.value,
          end: end.value,
        },
      }),
    ])
    if (id !== loadId) return
    accounts.value = a.data
    deals.value = d.data.items
    summary.value = d.data.summary
    movements.value = m.data.items
    movementCount.value = m.data.count
  } catch (e) {
    if (id === loadId) error.value = errorText(e)
  } finally {
    if (id === loadId) loading.value = false
  }
}
watch(q, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    void load()
  }, 300)
})
watch([state, start, end, accountId], () => {
  page.value = 1
  ledgerPage.value = 1
  void load()
})
watch([page, ledgerPage], () => void load())
onMounted(load)
onBeforeUnmount(() => {
  clearTimeout(searchTimer)
  loadId++
})
const editor = ref(false),
  editId = ref<number | null>(null)
const blank = () => ({
  entered_on: today(),
  due_on: null as string | null,
  payer: '',
  receiver: '',
  payer_inn: '',
  receiver_inn: '',
  client: '',
  executor: '',
  manager: '',
  amount: null as number | null,
  executor_rate: null as number | null,
  client_rate: null as number | null,
  manager_rate: 0 as number | null,
  comment: '',
  version: 1,
})
const form = reactive(blank())
const fields = [
  { key: 'payer', label: 'Плательщик' },
  { key: 'payer_inn', label: 'ИНН плательщика' },
  { key: 'receiver', label: 'Получатель' },
  { key: 'receiver_inn', label: 'ИНН получателя' },
  { key: 'client', label: 'Клиент' },
  { key: 'executor', label: 'Исполнитель' },
  { key: 'manager', label: 'Менеджер' },
] as const
const suggestions = ref<Record<string, string[]>>({})
let suggestionTimer: ReturnType<typeof setTimeout> | undefined
function suggest(field: string, q: string) {
  clearTimeout(suggestionTimer)
  suggestionTimer = setTimeout(async () => {
    try {
      const { data } = await http.get('/cashroom/suggestions', { params: { field, q } })
      suggestions.value[field] = data
    } catch {
      /* Manual input remains available. */
    }
  }, 200)
}
onBeforeUnmount(() => clearTimeout(suggestionTimer))
const rates = [
  { key: 'executor_rate', label: '% исполнителя' },
  { key: 'client_rate', label: '% клиента' },
  { key: 'manager_rate', label: '% менеджера' },
] as const
function edit(deal?: Deal) {
  editId.value = deal?.id ?? null
  Object.assign(form, blank())
  if (deal) {
    for (const key of Object.keys(form) as (keyof typeof form)[])
      (form as any)[key] = (deal as any)[key]
    for (const key of ['amount', 'executor_rate', 'client_rate', 'manager_rate'] as const)
      form[key] = Number(deal[key])
  }
  editor.value = true
}
const validDeal = computed(
  () =>
    form.entered_on &&
    form.payer.trim() &&
    form.receiver.trim() &&
    form.client.trim() &&
    form.executor.trim() &&
    Number(form.amount) > 0 &&
    form.executor_rate !== null &&
    form.client_rate !== null,
)
async function saveDeal() {
  if (saving.value || !validDeal.value) return
  saving.value = true
  try {
    const body = { ...form, manager_rate: form.manager_rate ?? 0 }
    if (editId.value) await http.put(`/cashroom/deals/${editId.value}`, body)
    else await http.post('/cashroom/deals', body)
    editor.value = false
    message.success('Сделка сохранена')
    await load()
    if (selected.value?.deal.id === editId.value) await openDetail(editId.value!)
  } catch (e) {
    message.error(errorText(e))
  } finally {
    saving.value = false
  }
}
const selected = ref<{ deal: Deal; movements: Movement[]; history: History[] } | null>(null),
  detailOpen = ref(false)
let detailId = 0
async function openDetail(id: number) {
  const request = ++detailId
  try {
    const { data } = await http.get(`/cashroom/deals/${id}`)
    if (request === detailId) {
      selected.value = data
      detailOpen.value = true
    }
  } catch (e) {
    message.error(errorText(e))
  }
}
const paymentOpen = ref(false)
const payment = reactive({
  operation_key: '',
  account_id: null as number | null,
  deal_id: null as number | null,
  kind: 'income',
  amount: null as number | null,
  occurred_on: today(),
  client: '',
  manager: '',
  comment: '',
  comment2: '',
})
function pay(kind: string, deal?: Deal) {
  Object.assign(payment, {
    operation_key: crypto.randomUUID(),
    account_id: accountId.value ?? accounts.value[0]?.id ?? null,
    deal_id: deal?.id ?? null,
    kind,
    amount: deal ? Math.max(0, Number(kind === 'receive' ? deal.receivable : deal.payable)) : null,
    occurred_on: today(),
    client: deal?.client ?? '',
    manager: deal?.manager ?? '',
    comment: '',
    comment2: '',
  })
  paymentOpen.value = true
}
async function savePayment() {
  if (saving.value || !payment.account_id || !payment.amount) return
  saving.value = true
  try {
    await http.post('/cashroom/movements', { ...payment })
    paymentOpen.value = false
    message.success('Операция записана')
    await load()
    if (selected.value && payment.deal_id === selected.value.deal.id)
      await openDetail(payment.deal_id!)
  } catch (e) {
    message.error(errorText(e))
  } finally {
    saving.value = false
  }
}
const accountOpen = ref(false),
  accountName = ref('')
async function saveAccount() {
  if (saving.value || !accountName.value.trim()) return
  saving.value = true
  try {
    const { data } = await http.post('/cashroom/accounts', { name: accountName.value.trim() })
    await load()
    payment.account_id = data.id
    accountOpen.value = false
    accountName.value = ''
    message.success('Касса создана')
  } catch (e) {
    message.error(errorText(e))
  } finally {
    saving.value = false
  }
}
const voidOpen = ref(false),
  voidId = ref<number | null>(null),
  reason = ref('')
function askVoid(m: Movement) {
  voidId.value = m.id
  reason.value = ''
  voidOpen.value = true
}
async function voidPayment() {
  if (saving.value || reason.value.trim().length < 3) return
  saving.value = true
  try {
    await http.post(`/cashroom/movements/${voidId.value}/void`, { reason: reason.value })
    voidOpen.value = false
    await load()
    if (selected.value) await openDetail(selected.value.deal.id)
    message.success('Операция отменена')
  } catch (e) {
    message.error(errorText(e))
  } finally {
    saving.value = false
  }
}
function closeEditor() {
  dialog.warning({
    title: 'Закрыть без сохранения?',
    positiveText: 'Закрыть',
    negativeText: 'Продолжить',
    onPositiveClick: () => {
      editor.value = false
    },
  })
}
const metrics = [
  ['amount', 'Сумма заходов'],
  ['receivable', 'Осталось получить'],
  ['payable', 'Осталось выдать'],
  ['profit', 'Прибыль по факту'],
] as const
const detailMetrics = [
  ['expected_received', 'К получению'],
  ['received', 'Получено'],
  ['receivable', 'Осталось получить'],
  ['expected_issued', 'К выдаче'],
  ['issued', 'Выдано'],
  ['payable', 'Осталось выдать'],
  ['revenue', 'Выручка'],
  ['salary', 'ЗП менеджера'],
  ['profit', 'Прибыль'],
] as const
const actionLabels: Record<string, string> = {
  deal_created: 'Сделка создана',
  deal_updated: 'Сделка изменена',
  payment_created: 'Платёж записан',
  payment_voided: 'Платёж отменён',
}
const labels: Record<string, string> = {
  ...Object.fromEntries(fields.map((f) => [f.key, f.label])),
  ...Object.fromEntries(rates.map((f) => [f.key, f.label])),
  amount: 'Сумма захода',
  entered_on: 'Дата захода',
  due_on: 'Дата получения (план)',
  comment: 'Комментарий',
  reason: 'Причина',
  occurred_on: 'Дата операции',
  kind: 'Операция',
  account_id: 'Касса',
  deal_id: 'Сделка',
  comment2: 'Комментарий 2',
}
function historyValue(v: unknown): string {
  if (v && typeof v === 'object' && 'before' in v && 'after' in v)
    return `${historyValue(v.before)} → ${historyValue(v.after)}`
  return v == null ? '—' : String(v)
}
</script>

<template>
  <main class="cashroom">
    <header class="top">
      <div>
        <div class="eyebrow">ФИНАНСЫ И РАСЧЁТЫ</div>
        <h1>Кэшеварня</h1>
      </div>
      <div class="actions">
        <NButton :loading="loading" aria-label="Обновить" @click="load"
          ><RefreshCw :size="16" /></NButton
        ><NButton type="primary" size="large" @click="edit()"
          ><template #icon><Plus :size="18" /></template>Новая сделка</NButton
        >
      </div>
    </header>
    <NAlert v-if="error" type="error" title="Данные не обновлены" class="notice"
      >{{ error }} <NButton size="small" @click="load">Повторить</NButton></NAlert
    >
    <div class="metrics">
      <div v-for="[key, label] in metrics" :key="key" class="metric">
        <span>{{ label }}</span
        ><strong>{{ summary[key] === undefined ? '—' : money(summary[key]) }}</strong>
      </div>
    </div>
    <div class="toolbar">
      <div class="tabs">
        <NButton :type="tab === 'deals' ? 'primary' : 'default'" @click="tab = 'deals'"
          >Сделки · {{ summary.count ?? 0 }}</NButton
        ><NButton :type="tab === 'cash' ? 'primary' : 'default'" @click="tab = 'cash'"
          >Кассы и операции</NButton
        >
      </div>
      <div class="dates">
        <NDatePicker
          v-model:formatted-value="start"
          value-format="yyyy-MM-dd"
          type="date"
          clearable
          placeholder="Период с"
          aria-label="Начало периода"
        /><NDatePicker
          v-model:formatted-value="end"
          value-format="yyyy-MM-dd"
          type="date"
          clearable
          placeholder="По дату"
          aria-label="Конец периода"
        />
      </div>
    </div>
    <NSpin :show="loading">
      <section v-if="tab === 'deals'" class="panel">
        <div class="filters">
          <NInput
            v-model:value="q"
            clearable
            placeholder="Клиент, исполнитель, компания или ИНН"
            aria-label="Поиск сделок"
          /><NSelect v-model:value="state" :options="states" aria-label="Статус сделки" />
        </div>
        <div class="registry-head">
          <span>Сделка и участники</span><span>Сумма захода</span><span>Получение</span
          ><span>Выдача</span><span>Действия</span>
        </div>
        <article v-for="deal in deals" :key="deal.id" class="deal-row">
          <div class="identity">
            <button class="deal-link" @click="openDetail(deal.id)">{{ deal.client }}</button
            ><span>{{ deal.payer }} → {{ deal.receiver }}</span
            ><small>№ {{ deal.id }} · {{ date(deal.entered_on) }} · {{ deal.executor }}</small
            ><NTag
              size="small"
              :bordered="false"
              :type="
                deal.status === 'overdue'
                  ? 'error'
                  : deal.status === 'closed'
                    ? 'success'
                    : 'default'
              "
              >{{ states.find((s) => s.value === deal.status)?.label }}</NTag
            >
          </div>
          <div class="cell">
            <span class="mobile-label">Сумма захода</span><strong>{{ money(deal.amount) }}</strong
            ><small>Прибыль {{ money(deal.profit) }}</small>
          </div>
          <div class="cell">
            <span class="mobile-label">Получение</span><strong>{{ money(deal.receivable) }}</strong
            ><small>Получено {{ money(deal.received) }}</small
            ><small v-if="deal.due_on" :class="{ late: deal.status === 'overdue' }"
              >До {{ date(deal.due_on) }}</small
            >
          </div>
          <div class="cell">
            <span class="mobile-label">Выдача</span><strong>{{ money(deal.payable) }}</strong
            ><small>Выдано {{ money(deal.issued) }}</small>
          </div>
          <div class="row-actions">
            <NButton size="small" @click="pay('receive', deal)"
              ><template #icon><ArrowDownLeft :size="15" /></template>Получить</NButton
            ><NButton size="small" @click="pay('issue', deal)"
              ><template #icon><ArrowUpRight :size="15" /></template>Выдать</NButton
            ><NButton size="small" quaternary @click="openDetail(deal.id)">Подробнее</NButton>
          </div>
        </article>
        <NEmpty
          v-if="!deals.length && !loading"
          class="empty"
          :description="
            q || state !== 'all' || start || end
              ? 'Сделок по этим условиям нет'
              : 'Добавьте первую сделку'
          "
          ><template #extra><NButton @click="edit()">Новая сделка</NButton></template></NEmpty
        >
        <footer>
          <span
            >Плановая прибыль:
            {{ summary.planned_profit === undefined ? '—' : money(summary.planned_profit) }}</span
          ><NPagination
            v-model:page="page"
            :item-count="Number(summary.count || 0)"
            :page-size="30"
            :page-slot="5"
            simple
          />
        </footer>
      </section>
      <section v-else>
        <div class="accounts">
          <button
            v-for="a in accounts"
            :key="a.id"
            class="account"
            :class="{ active: accountId === a.id }"
            @click="accountId = accountId === a.id ? null : a.id"
          >
            <Wallet :size="20" /><span>{{ a.name }}</span
            ><strong>{{ money(a.balance) }}</strong></button
          ><NButton dashed @click="accountOpen = true">+ Добавить кассу</NButton>
        </div>
        <div class="panel">
          <div class="toolbar">
            <h2>Журнал операций</h2>
            <div class="actions">
              <NButton @click="pay('income')">+ Приход</NButton
              ><NButton @click="pay('expense')">− Расход</NButton
              ><NButton @click="pay('opening')">Начальный остаток</NButton>
            </div>
          </div>
          <p v-if="accountId" class="muted">
            Выбрана касса: {{ accounts.find((a) => a.id === accountId)?.name }}
            <NButton text @click="accountId = null">Показать все</NButton>
          </p>
          <article
            v-for="m in movements"
            :key="m.id"
            class="movement"
            :class="{ voided: m.voided }"
          >
            <div>
              <strong>{{ kinds[m.kind] }} · {{ m.account_name }}</strong
              ><small
                >{{ date(m.occurred_on) }} · {{ m.client || 'Без клиента' }}
                {{ m.manager ? `· ${m.manager}` : '' }}</small
              >
              <p v-if="m.comment">{{ m.comment }}</p>
              <p v-if="m.comment2">{{ m.comment2 }}</p>
              <NButton v-if="m.deal_id" text @click="openDetail(m.deal_id)"
                >Сделка № {{ m.deal_id }}</NButton
              >
            </div>
            <div class="cell">
              <strong :class="{ late: ['issue', 'expense'].includes(m.kind) }"
                >{{ ['issue', 'expense'].includes(m.kind) ? '−' : '+'
                }}{{ money(m.amount) }}</strong
              ><span v-if="m.voided">Отменена</span
              ><NButton v-else size="tiny" quaternary @click="askVoid(m)"
                >Отменить операцию</NButton
              >
            </div>
          </article>
          <NEmpty
            v-if="!movements.length && !loading"
            class="empty"
            description="Операций пока нет"
          />
          <footer>
            <span>{{ movementCount }} операций</span
            ><NPagination
              v-model:page="ledgerPage"
              :item-count="movementCount"
              :page-size="30"
              simple
            />
          </footer>
        </div>
      </section>
    </NSpin>

    <NModal
      :show="editor"
      preset="card"
      :title="editId ? `Сделка № ${editId}` : 'Новая сделка'"
      class="cash-modal"
      :mask-closable="false"
      :close-on-esc="false"
      @close="closeEditor"
    >
      <form @submit.prevent="saveDeal">
        <div class="form-grid">
          <label
            >Дата захода<NDatePicker
              v-model:formatted-value="form.entered_on"
              value-format="yyyy-MM-dd"
              type="date"
              :clearable="false" /></label
          ><label
            >Дата получения (план)<NDatePicker
              v-model:formatted-value="form.due_on"
              value-format="yyyy-MM-dd"
              type="date"
              clearable
          /></label>
        </div>
        <h3>Участники</h3>
        <div class="form-grid">
          <label v-for="f in fields" :key="f.key"
            >{{ f.label
            }}<NAutoComplete
              v-model:value="form[f.key]"
              :options="suggestions[f.key] || []"
              @update:value="suggest(f.key, $event)"
              @focus="suggest(f.key, form[f.key])"
              :aria-label="f.label"
              :maxlength="f.key.includes('inn') ? 12 : 200"
              :placeholder="f.label"
          /></label>
        </div>
        <h3>Расчёты</h3>
        <div class="form-grid">
          <label
            >Сумма захода, ₽<NInputNumber
              v-model:value="form.amount"
              :min="0.01"
              :precision="2"
              :show-button="false"
              aria-label="Сумма захода" /></label
          ><label v-for="r in rates" :key="r.key"
            >{{ r.label
            }}<NInputNumber
              v-model:value="form[r.key]"
              :min="0"
              :max="100"
              :precision="3"
              :show-button="false"
              :aria-label="r.label"
          /></label>
        </div>
        <label class="comment"
          >Комментарий<NInput
            v-model:value="form.comment"
            type="textarea"
            :maxlength="5000"
            :autosize="{ minRows: 2, maxRows: 5 }"
        /></label>
        <div class="form-footer">
          <NButton :disabled="saving" @click="closeEditor">Отмена</NButton
          ><NButton type="primary" attr-type="submit" :loading="saving" :disabled="!validDeal"
            >Сохранить сделку</NButton
          >
        </div>
      </form>
    </NModal>
    <NModal
      v-model:show="detailOpen"
      preset="card"
      :title="`Сделка № ${selected?.deal.id ?? ''}`"
      class="cash-modal"
    >
      <template v-if="selected"
        ><div class="toolbar">
          <h2>{{ selected.deal.client }}</h2>
          <NButton @click="edit(selected.deal)">Редактировать</NButton>
        </div>
        <div class="form-grid detail-fields">
          <div v-for="f in fields" :key="f.key">
            <small>{{ f.label }}</small
            ><strong>{{ selected.deal[f.key] || '—' }}</strong>
          </div>
          <div><small>Дата захода</small>{{ date(selected.deal.entered_on) }}</div>
          <div><small>Дата получения (план)</small>{{ date(selected.deal.due_on) }}</div>
          <div><small>Сумма захода</small>{{ money(selected.deal.amount) }}</div>
          <div v-for="r in rates" :key="r.key">
            <small>{{ r.label }}</small
            >{{ selected.deal[r.key] }}%
          </div>
        </div>
        <p v-if="selected.deal.comment">{{ selected.deal.comment }}</p>
        <div class="detail-metrics">
          <div v-for="[key, label] in detailMetrics" :key="key">
            <small>{{ label }}</small
            ><strong>{{ money(selected.deal[key]) }}</strong>
          </div>
        </div>
        <div class="actions">
          <NButton type="primary" @click="pay('receive', selected.deal)">Получить</NButton
          ><NButton @click="pay('issue', selected.deal)">Выдать</NButton>
        </div>
        <h3>Платежи</h3>
        <article v-for="m in selected.movements" :key="m.id" class="movement">
          <div>
            <strong>{{ kinds[m.kind] }} · {{ money(m.amount) }}</strong
            ><small>{{ date(m.occurred_on) }} · {{ m.account_name }}</small
            ><span>{{ m.comment }}</span>
          </div>
          <span v-if="m.voided">Отменена</span
          ><NButton v-else size="small" @click="askVoid(m)">Отменить</NButton>
        </article>
        <NEmpty v-if="!selected.movements.length" description="Платежей пока нет" />
        <h3>История изменений</h3>
        <details v-for="h in selected.history" :key="h.id" class="history">
          <summary>
            {{ actionLabels[h.action] || h.action }} · {{ h.actor }} · {{ date(h.at) }}
          </summary>
          <div v-for="(v, k) in h.changes" :key="k">
            <template v-if="k !== 'operation_key'"
              ><b>{{ labels[k] || k }}:</b> {{ historyValue(v) }}</template
            >
          </div>
        </details></template
      >
    </NModal>
    <NModal
      v-model:show="paymentOpen"
      preset="card"
      :title="`${kinds[payment.kind]}${payment.deal_id ? ` · сделка № ${payment.deal_id}` : ''}`"
      class="cash-modal compact"
      :mask-closable="false"
    >
      <form @submit.prevent="savePayment">
        <div class="form-grid">
          <label
            >Касса<NSelect
              v-model:value="payment.account_id"
              :options="accountOptions"
              placeholder="Выберите кассу" /></label
          ><label
            >Дата<NDatePicker
              v-model:formatted-value="payment.occurred_on"
              value-format="yyyy-MM-dd"
              type="date"
              :clearable="false" /></label
          ><label
            >Сумма, ₽<NInputNumber
              v-model:value="payment.amount"
              :min="0.01"
              :precision="2"
              :show-button="false" /></label
          ><label>Клиент<NInput v-model:value="payment.client" maxlength="200" /></label
          ><label>Менеджер<NInput v-model:value="payment.manager" maxlength="200" /></label>
        </div>
        <NButton v-if="!accounts.length" class="comment" @click="accountOpen = true"
          >Создать кассу</NButton
        ><label class="comment"
          >Комментарий<NInput
            v-model:value="payment.comment"
            type="textarea"
            maxlength="5000" /></label
        ><label class="comment"
          >Комментарий 2<NInput v-model:value="payment.comment2" maxlength="5000"
        /></label>
        <div class="form-footer">
          <NButton :disabled="saving" @click="paymentOpen = false">Отмена</NButton
          ><NButton
            type="primary"
            attr-type="submit"
            :loading="saving"
            :disabled="!payment.account_id || !payment.amount || payment.amount <= 0"
            >Записать {{ money(payment.amount) }}</NButton
          >
        </div>
      </form>
    </NModal>
    <NModal v-model:show="accountOpen" preset="card" title="Новая касса" class="cash-modal compact"
      ><form @submit.prevent="saveAccount">
        <label>Название<NInput v-model:value="accountName" maxlength="100" autofocus /></label>
        <div class="form-footer">
          <NButton
            type="primary"
            attr-type="submit"
            :loading="saving"
            :disabled="!accountName.trim()"
            >Создать кассу</NButton
          >
        </div>
      </form></NModal
    >
    <NModal v-model:show="voidOpen" preset="card" title="Отмена операции" class="cash-modal compact"
      ><form @submit.prevent="voidPayment">
        <p>Сумма будет исключена из остатка кассы и расчётов сделки. Запись останется в истории.</p>
        <label
          >Причина отмены<NInput v-model:value="reason" type="textarea" maxlength="1000"
        /></label>
        <div class="form-footer">
          <NButton @click="voidOpen = false">Назад</NButton
          ><NButton
            type="error"
            attr-type="submit"
            :loading="saving"
            :disabled="reason.trim().length < 3"
            >Отменить операцию</NButton
          >
        </div>
      </form></NModal
    >
  </main>
</template>

<style scoped>
.cashroom {
  width: 100%;
  min-width: 0;
  max-width: 1600px;
  margin: auto;
  padding: 24px;
  box-sizing: border-box;
  container-type: inline-size;
}
.top,
.toolbar,
.actions,
.tabs,
.dates {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.top,
.toolbar {
  justify-content: space-between;
}
.top {
  margin-bottom: 24px;
}
.eyebrow {
  font-size: 11px;
  letter-spacing: 2px;
  color: var(--text-color-3, #777);
}
h1 {
  font-size: 30px;
  letter-spacing: -1px;
  margin: 4px 0;
}
h2 {
  font-size: 18px;
  margin: 0;
}
h3 {
  margin: 24px 0 12px;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.metric,
.panel,
.account {
  border: 1px solid var(--border-color, #e5e7eb);
  background: var(--card-color, #fff);
  border-radius: 14px;
}
.metric {
  padding: 18px;
}
.metric span,
small,
.muted {
  color: var(--text-color-3, #777);
  font-size: 12px;
}
.metric strong {
  display: block;
  font-size: clamp(17px, 2.1cqw, 27px);
  letter-spacing: -0.5px;
  margin-top: 8px;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.toolbar {
  margin: 16px 0;
}
.dates {
  max-width: 100%;
}
.dates :deep(.n-date-picker) {
  width: 155px;
}
.panel {
  padding: 18px;
  min-width: 0;
}
.filters {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(150px, 210px);
  gap: 12px;
  margin-bottom: 20px;
}
.registry-head,
.deal-row {
  display: grid;
  grid-template-columns: minmax(0, 1.8fr) repeat(3, minmax(0, 1fr)) 110px;
  gap: 16px;
}
.registry-head {
  font-size: 12px;
  color: var(--text-color-3, #777);
  padding: 0 0 12px;
}
.deal-row {
  padding: 18px 0;
  border-top: 1px solid var(--border-color, #e5e7eb);
  align-items: start;
}
.deal-row > * {
  min-width: 0;
  overflow-wrap: anywhere;
}
.identity,
.cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
}
.identity > span {
  font-size: 12px;
}
.deal-link {
  border: 0;
  padding: 0;
  background: none;
  color: inherit;
  font: inherit;
  font-weight: 650;
  text-align: left;
  cursor: pointer;
  overflow-wrap: anywhere;
}
.deal-link:hover {
  text-decoration: underline;
}
.identity :deep(.n-tag) {
  margin-top: 4px;
}
.cell strong {
  font-size: 14px;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.row-actions {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.mobile-label {
  display: none;
}
.late {
  color: #d03050 !important;
}
footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  margin-top: 20px;
  color: var(--text-color-3, #777);
  font-size: 12px;
}
.empty {
  padding: 48px 0;
}
.accounts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: 12px;
  margin: 20px 0;
}
.account {
  padding: 18px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  text-align: left;
  color: inherit;
  font: inherit;
  cursor: pointer;
  overflow-wrap: anywhere;
}
.account strong {
  width: 100%;
  font-size: 24px;
  font-variant-numeric: tabular-nums;
}
.account.active {
  border-color: #18a058;
  box-shadow: 0 0 0 1px #18a058;
}
.movement {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 0;
  border-bottom: 1px solid var(--border-color, #e5e7eb);
  overflow-wrap: anywhere;
}
.movement > div {
  min-width: 0;
}
.movement small {
  display: block;
  margin-top: 5px;
}
.movement p {
  margin: 4px 0;
}
.voided {
  opacity: 0.6;
}
.voided strong {
  text-decoration: line-through;
}
.notice {
  margin-bottom: 16px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.form-grid > * {
  min-width: 0;
}
label {
  display: block;
  font-size: 12px;
}
label > :deep(*) {
  margin-top: 6px;
}
.form-grid :deep(.n-date-picker),
.form-grid :deep(.n-input-number) {
  width: 100%;
}
.comment {
  margin-top: 16px;
}
.form-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 24px;
}
.detail-fields small,
.detail-metrics small {
  display: block;
  margin-bottom: 4px;
}
.detail-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  background: var(--body-color, #f5f7f8);
  border-radius: 12px;
  padding: 16px;
  margin: 20px 0;
}
.detail-metrics strong {
  font-variant-numeric: tabular-nums;
}
.history {
  padding: 12px 0;
  border-bottom: 1px solid var(--border-color, #eee);
  font-size: 12px;
}
.history summary {
  cursor: pointer;
}
.history div {
  margin-top: 6px;
  overflow-wrap: anywhere;
}
@container (max-width:900px) {
  .registry-head {
    display: none;
  }
  .deal-row {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
  }
  .identity {
    grid-column: 1/-1;
  }
  .row-actions {
    grid-column: 1/-1;
    flex-direction: row;
    flex-wrap: wrap;
  }
  .mobile-label {
    display: block;
    color: var(--text-color-3, #777);
    font-size: 12px;
  }
  .metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 600px) {
  .cashroom {
    padding: 12px;
  }
  .filters {
    grid-template-columns: 1fr;
  }
  .form-grid,
  .detail-metrics {
    grid-template-columns: 1fr;
  }
  .dates {
    display: grid;
    grid-template-columns: 1fr 1fr;
    width: 100%;
  }
  .dates :deep(.n-date-picker) {
    width: 100%;
  }
  .movement {
    flex-wrap: wrap;
  }
  .top {
    gap: 16px;
  }
  .metric {
    padding: 12px;
  }
  .panel {
    padding: 12px;
  }
}
</style>
<style>
.cash-modal.n-card {
  width: min(760px, calc(100vw - 24px));
  max-height: calc(100dvh - 32px);
  overflow-y: auto;
  overflow-wrap: anywhere;
  border-radius: 16px;
}
.cash-modal.compact.n-card {
  width: min(520px, calc(100vw - 24px));
}
</style>
