<script setup lang="ts">
import {
  NButton,
  NDatePicker,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NModal,
  NRadio,
  NRadioGroup,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NTooltip,
  useMessage,
} from 'naive-ui'
import { Plus, Trash2 } from 'lucide-vue-next'
import type { SelectOption } from 'naive-ui'
import { computed, onMounted, ref, watch } from 'vue'

import type { ChatDetail } from '@/entities/chat/types'
import type { BotListItem } from '@/entities/bot/types'
import {
  getCachedLeadDetail,
  getChatDealsSnapshot,
  pickPreferredLeadId,
  setCachedLeadDetail,
  setChatDealsSnapshot,
} from '@/features/chats/deals-cache'
import { getLead, listContactLeads, listTreeServiceTypes, patchLead } from '@/features/leads/api'
import { listOptOrders } from '@/features/leads/opt-api'
import {
  OPT_PERIOD_OPTIONS,
  buildLeadDealPatch,
  readLeadDealFields,
  summarizeTreeLines,
  summarizeTreePayments,
  treeDueAmount,
  treePaymentStatus,
} from '@/features/leads/order-fields'
import {
  OPT_PAYMENT_RECIPIENT_OPTIONS,
  OPT_PAYMENT_TYPE_OPTIONS,
  optPaymentStatusLabel,
  optPaymentTypeLabel,
} from '@/features/leads/opt-types'
import { serviceOptionsForBot } from '@/features/leads/service-types'
import {
  TREE_SERVICE_TYPE_FALLBACK,
  newTreeLineId,
  treeLineTotal,
  type TreeOrderLine,
  type TreePayment,
  type TreeServiceTypeOption,
} from '@/features/leads/tree-service-types'
import { leadCommentItems } from '@/features/leads/comments'
import type { LeadDetail, LeadListItem } from '@/features/leads/types'
import { useChatsStore } from '@/features/chats/store'
import OptOrdersPanel from '@/widgets/chat/OptOrdersPanel.vue'
import { AppError } from '@/shared/api/http'

const props = defineProps<{
  chat: ChatDetail | null
  bots?: BotListItem[]
  leadStatusOptions: SelectOption[]
  wonStatusId: number | null
  lostStatusId: number | null
}>()

const store = useChatsStore()
const message = useMessage()

const leadItems = ref<LeadListItem[]>([])
const leadDetail = ref<LeadDetail | null>(null)
const loadingLeads = ref(false)
const loadingLead = ref(false)
const savingFields = ref(false)

const selectedLeadId = computed({
  get: () => store.selectedLeadId,
  set: (value: number | null) => {
    void store.selectLead(value)
  },
})

const hasSelectedOpenLead = computed(
  () => leadDetail.value != null && leadDetail.value.closed_at == null,
)

const service = ref('')
const period = ref<string | null>(null)
const quantity = ref<number | null>(null)
const cost = ref<number | null>(null)
const costPrice = ref<number | null>(null)
const treeCatalog = ref<TreeServiceTypeOption[]>([...TREE_SERVICE_TYPE_FALLBACK])
const treeLines = ref<TreeOrderLine[]>([])
const treeAdjDirection = ref<'decrease' | 'increase'>('decrease')
const treeAdjAmount = ref<number | null>(null)
const treePayments = ref<TreePayment[]>([])
/** Unsaved order edits — block applyLeadDetail from WS/list refresh wiping the form. */
const orderFormDirty = ref(false)
const paymentOpen = ref(false)
const paymentForm = ref({
  amount: null as number | null,
  paid_at: Date.now() as number,
  payment_type: 'wire' as TreePayment['payment_type'],
  recipient: 'orange' as TreePayment['recipient'],
})
const commentDraft = ref('')
const commentsOpen = ref(false)
const optPaymentsReady = ref(true)
const periodOptions = OPT_PERIOD_OPTIONS

const serviceOptions = computed<SelectOption[]>(() => {
  const botId = props.chat?.bot_id
  const bot = botId != null ? props.bots?.find((row) => row.id === botId) : null
  return serviceOptionsForBot(bot?.service_types, service.value)
})

const isOptService = computed(() => service.value === 'ОПТ')
const isTreesService = computed(() => service.value === 'Деревья')

const treeTypeOptions = computed<SelectOption[]>(() =>
  treeCatalog.value
    .filter((row) => row.is_active)
    .map((row) => ({
      label: row.unit_price != null ? `${row.label} · ${row.unit_price} ₽` : row.label,
      value: row.type_code,
    })),
)

const treeSignedAdjustment = computed(() => {
  const amount = Number(treeAdjAmount.value || 0)
  if (!amount) return 0
  return treeAdjDirection.value === 'increase' ? amount : -amount
})

const treeBaseTotal = computed(() => summarizeTreeLines(treeLines.value).base_cost ?? 0)
const treeDueTotal = computed(() => treeDueAmount(treeLines.value, treeSignedAdjustment.value))
const treeAmountPaid = computed(() => summarizeTreePayments(treePayments.value))
const treeAmountRemaining = computed(() =>
  Math.max(0, treeDueTotal.value - treeAmountPaid.value),
)
const treePayStatus = computed(() => treePaymentStatus(treeDueTotal.value, treeAmountPaid.value))

const leadComments = computed(() =>
  leadDetail.value ? leadCommentItems(leadDetail.value) : [],
)

const canCloseWon = computed(
  () =>
    hasSelectedOpenLead.value &&
    (!isOptService.value || (Boolean(period.value) && optPaymentsReady.value)),
)

const closeWonTooltip = computed(() => {
  if (!hasSelectedOpenLead.value || props.wonStatusId == null) return null
  if (isOptService.value && !period.value) {
    return 'Для ОПТ сначала выберите период.'
  }
  if (isOptService.value && !optPaymentsReady.value) {
    return 'Закрыть как успешную можно только когда все заявки ОПТ оплачены полностью.'
  }
  return null
})

const leadOptions = computed<SelectOption[]>(() =>
  leadItems.value.map((lead) => ({
    label: `Сделка №${lead.id} — ${statusLabel(lead)}`,
    value: lead.id,
  })),
)

const selectedLeadStatusId = computed({
  get: () => leadDetail.value?.status_id ?? null,
  set: (statusId: number | null) => {
    if (statusId == null || leadDetail.value == null) return
    void updateSelectedLeadStatus(statusId)
  },
})

function statusLabel(lead: LeadListItem): string {
  if (lead.closed_at) return 'закрыта'
  return lead.status_label ?? 'открыта'
}

function markOrderFormDirty(): void {
  orderFormDirty.value = true
}

function resetOrderForm(): void {
  orderFormDirty.value = false
  service.value = ''
  period.value = null
  quantity.value = null
  cost.value = null
  costPrice.value = null
  treeLines.value = []
  treeAdjDirection.value = 'decrease'
  treeAdjAmount.value = null
  treePayments.value = []
  commentDraft.value = ''
}

function unitPriceFor(type: string): number | null {
  const row = treeCatalog.value.find((item) => item.type_code === type)
  return row?.unit_price ?? null
}

function addTreeLine(): void {
  markOrderFormDirty()
  treeLines.value = [
    ...treeLines.value,
    {
      id: newTreeLineId(),
      type: '',
      quantity: 1,
      unit_price: null,
    },
  ]
}

function removeTreeLine(id: string): void {
  markOrderFormDirty()
  treeLines.value = treeLines.value.filter((row) => row.id !== id)
}

function patchTreeLine(id: string, patch: Partial<TreeOrderLine>): void {
  markOrderFormDirty()
  treeLines.value = treeLines.value.map((row) => (row.id === id ? { ...row, ...patch } : row))
}

function onTreeTypeChange(id: string, type: string): void {
  const current = treeLines.value.find((row) => row.id === id)
  const catalogPrice = unitPriceFor(type)
  patchTreeLine(id, {
    type,
    unit_price:
      current?.unit_price != null && current.unit_price > 0
        ? current.unit_price
        : catalogPrice,
  })
}

function onTreeAdjDirection(value: string | number): void {
  markOrderFormDirty()
  treeAdjDirection.value = value === 'increase' ? 'increase' : 'decrease'
}

function onTreeAdjAmount(value: number | null): void {
  markOrderFormDirty()
  treeAdjAmount.value = value
}

function buildTreeLinesPayload(): TreeOrderLine[] {
  return treeLines.value
    .filter((row) => row.type.trim())
    .map((row) => ({
      id: row.id,
      type: row.type.trim(),
      quantity: row.quantity ?? null,
      unit_price: row.unit_price ?? null,
    }))
}

function applyLeadDetail(detail: LeadDetail, options?: { force?: boolean }): void {
  // Keep badge/status in sync, but never wipe in-progress position edits.
  if (!options?.force && orderFormDirty.value && leadDetail.value?.id === detail.id) {
    leadDetail.value = detail
    return
  }
  orderFormDirty.value = false
  leadDetail.value = detail
  const fields = readLeadDealFields(detail.custom_fields)
  service.value = fields.order?.service?.toString() ?? ''
  period.value = fields.order?.period?.toString() || null
  const qty = fields.order?.quantity
  quantity.value = qty == null || qty === '' ? null : Number(qty)
  const costRaw = fields.order?.cost
  cost.value = costRaw == null || costRaw === '' ? null : Number(costRaw)
  const cpRaw = fields.order?.cost_price
  costPrice.value = cpRaw == null || cpRaw === '' ? null : Number(cpRaw)
  const lines = fields.order?.tree_lines ?? []
  treeLines.value = Array.isArray(lines)
    ? lines.map((row) => ({
        id: row.id || newTreeLineId(),
        type: row.type,
        quantity: row.quantity == null ? null : Number(row.quantity),
        unit_price: row.unit_price == null ? null : Number(row.unit_price),
      }))
    : []
  const adj = Number(fields.order?.tree_adjustment || 0)
  if (adj < 0) {
    treeAdjDirection.value = 'decrease'
    treeAdjAmount.value = Math.abs(adj)
  } else if (adj > 0) {
    treeAdjDirection.value = 'increase'
    treeAdjAmount.value = adj
  } else {
    treeAdjDirection.value = 'decrease'
    treeAdjAmount.value = null
  }
  treePayments.value = [...(fields.order?.tree_payments ?? [])]
  commentDraft.value = ''
}

onMounted(() => {
  void listTreeServiceTypes()
    .then((items) => {
      if (items.length) treeCatalog.value = items
    })
    .catch(() => {
      /* keep fallback */
    })
})

async function refreshOptPaymentGate(leadId: number | null): Promise<void> {
  if (!isOptService.value || leadId == null) {
    optPaymentsReady.value = true
    return
  }
  try {
    const orders = await listOptOrders(leadId)
    optPaymentsReady.value =
      orders.length === 0 || orders.every((row) => row.payment_status === 'paid')
  } catch {
    optPaymentsReady.value = true
  }
}

function isLeadDetailStaleVsList(leadId: number, detail: LeadDetail): boolean {
  const listRow = leadItems.value.find((lead) => lead.id === leadId)
  if (listRow == null) return false
  // List endpoint was refreshed (e.g. after reopen) but detail cache still has old closed_at.
  return Boolean(detail.closed_at) !== Boolean(listRow.closed_at)
}

async function loadLeadDetail(leadId: number, forceRefresh = false): Promise<void> {
  if (!forceRefresh) {
    const cached = getCachedLeadDetail(leadId)
    if (cached && !isLeadDetailStaleVsList(leadId, cached)) {
      applyLeadDetail(cached)
      await refreshOptPaymentGate(cached.id)
      return
    }
  }
  // Keep current detail visible while refreshing — don't freeze the whole side panel.
  loadingLead.value = leadDetail.value?.id !== leadId
  try {
    const detail = await getLead(leadId)
    setCachedLeadDetail(detail)
    applyLeadDetail(detail)
    await refreshOptPaymentGate(detail.id)
  } catch {
    if (leadDetail.value?.id === leadId) {
      leadDetail.value = null
      resetOrderForm()
    }
  } finally {
    loadingLead.value = false
  }
}

async function loadLeads(forceRefresh = false): Promise<void> {
  const chat = props.chat
  if (chat == null) {
    leadItems.value = []
    leadDetail.value = null
    resetOrderForm()
    return
  }
  if (chat.assigned_group_id == null) {
    leadItems.value = []
    leadDetail.value = null
    resetOrderForm()
    return
  }

  const cached = !forceRefresh ? getChatDealsSnapshot(chat.id) : null
  if (cached) {
    leadItems.value = cached.leadItems
    const preferredId =
      selectedLeadId.value != null &&
      cached.leadItems.some((lead) => lead.id === selectedLeadId.value)
        ? selectedLeadId.value
        : cached.preferredLeadId
    if (preferredId != null) {
      const detail = getCachedLeadDetail(preferredId)
      if (detail) applyLeadDetail(detail)
      else {
        leadDetail.value = null
        resetOrderForm()
      }
    } else {
      leadDetail.value = null
      resetOrderForm()
    }
    // Do not return early on «fresh» snapshot: list/detail can be stale after admin/SQL reopen
    // (dropdown already shows open status while badge still says «закрыта»).
  } else {
    // No cache for this chat — clear previous chat's deals immediately.
    leadItems.value = []
    leadDetail.value = null
    resetOrderForm()
  }

  loadingLeads.value = !cached && leadItems.value.length === 0
  try {
    const data = await listContactLeads(chat.contact_id, {
      group_id: chat.assigned_group_id ?? undefined,
      limit: 100,
    })
    // Chat may have changed while request was in flight.
    if (props.chat?.id !== chat.id) return
    const items = data.items.filter(
      (lead) =>
        lead.chat_id === chat.id ||
        (chat.current_lead != null && lead.id === chat.current_lead.id),
    )
    leadItems.value = items
    const preferredId =
      selectedLeadId.value != null && items.some((lead) => lead.id === selectedLeadId.value)
        ? selectedLeadId.value
        : pickPreferredLeadId(items)
    setChatDealsSnapshot(chat.id, items, preferredId)
    if (props.chat?.id !== chat.id) return
    await store.selectLead(preferredId)
    // selectLead may no-op when id unchanged — always re-apply fresh detail after list refresh
    // (fixes badge «закрыта» after SQL/admin reopen while dropdown already shows open status).
    const idToShow = selectedLeadId.value ?? preferredId
    if (idToShow != null) {
      await loadLeadDetail(idToShow, true)
      store.bumpOptOrdersRefresh()
    }
  } catch (err) {
    if (props.chat?.id === chat.id) {
      if (leadItems.value.length === 0) {
        leadItems.value = []
      }
      message.error(
        err instanceof AppError ? err.message : 'Не удалось загрузить сделки по контакту',
      )
    }
  } finally {
    loadingLeads.value = false
  }
}

watch(
  () => [props.chat?.id, props.chat?.current_lead?.id] as const,
  (next, prev) => {
    // Switching chats discards local draft; same-chat lead refresh keeps dirty form.
    if (prev != null && next[0] !== prev[0]) {
      orderFormDirty.value = false
    }
    void loadLeads()
  },
  { immediate: true },
)

watch(
  selectedLeadId,
  (id, prevId) => {
    if (id !== prevId) {
      orderFormDirty.value = false
    }
    if (id == null) {
      leadDetail.value = null
      resetOrderForm()
      return
    }
    void loadLeadDetail(id)
  },
  { immediate: true },
)

watch(
  () => store.optOrdersRefreshNonce,
  () => {
    void refreshOptPaymentGate(selectedLeadId.value)
  },
)

async function persistOrderFields(): Promise<void> {
  if (!hasSelectedOpenLead.value || leadDetail.value == null) return
  savingFields.value = true
  try {
    if (service.value.trim() === 'ОПТ' && !period.value) {
      message.warning('Для ОПТ выберите период')
      savingFields.value = false
      return
    }
    const svc = service.value.trim()
    const treePayload = svc === 'Деревья' ? buildTreeLinesPayload() : []
    const treeTotals = summarizeTreeLines(treePayload)
    const due =
      svc === 'Деревья' ? treeDueAmount(treePayload, treeSignedAdjustment.value) : undefined
    const paid = svc === 'Деревья' ? summarizeTreePayments(treePayments.value) : undefined
    const customFields = buildLeadDealPatch(leadDetail.value.custom_fields, {
      order: {
        service: svc || undefined,
        period: svc === 'ОПТ' ? period.value || undefined : undefined,
        quantity:
          svc === 'Деревья' ? (treeTotals.quantity ?? undefined) : (quantity.value ?? undefined),
        cost: svc === 'Деревья' ? (due ?? undefined) : (cost.value ?? undefined),
        cost_price: svc === 'Деревья' ? undefined : (costPrice.value ?? undefined),
        tree_lines: svc === 'Деревья' ? treePayload : undefined,
        tree_payments: svc === 'Деревья' ? treePayments.value : undefined,
        tree_adjustment: svc === 'Деревья' ? treeSignedAdjustment.value : undefined,
        amount_paid: paid,
      },
    })
    const updated = await patchLead(leadDetail.value.id, { custom_fields: customFields })
    setCachedLeadDetail(updated)
    applyLeadDetail(updated, { force: true })
    message.success('Сохранено')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить сделку')
  } finally {
    savingFields.value = false
  }
}

function openTreePaymentModal(): void {
  paymentForm.value = {
    amount: treeAmountRemaining.value > 0 ? Math.round(treeAmountRemaining.value) : null,
    paid_at: Date.now(),
    payment_type: 'wire',
    recipient: 'orange',
  }
  paymentOpen.value = true
}

async function submitTreePayment(): Promise<void> {
  if (paymentForm.value.amount == null || paymentForm.value.amount <= 0) {
    message.warning('Укажите сумму оплаты')
    return
  }
  markOrderFormDirty()
  treePayments.value = [
    ...treePayments.value,
    {
      id: `tp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      amount: Number(paymentForm.value.amount),
      paid_at: new Date(paymentForm.value.paid_at).toISOString(),
      payment_type: paymentForm.value.payment_type,
      recipient: paymentForm.value.recipient,
    },
  ]
  paymentOpen.value = false
  await persistOrderFields()
}

function paymentStatusClass(status: string): string {
  if (status === 'paid') return 'deal-side__pay-pill deal-side__pay-pill--ok'
  if (status === 'partial') return 'deal-side__pay-pill deal-side__pay-pill--warn'
  return 'deal-side__pay-pill deal-side__pay-pill--danger'
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    maximumFractionDigits: 0,
  }).format(Math.round(value))
}

async function updateSelectedLeadStatus(statusId: number): Promise<void> {
  if (!hasSelectedOpenLead.value || leadDetail.value == null) return
  try {
    const updated = await patchLead(leadDetail.value.id, { status_id: statusId })
    setCachedLeadDetail(updated)
    applyLeadDetail(updated)
    await loadLeads(true)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось изменить статус')
  }
}

async function onCreateLead(): Promise<void> {
  try {
    const created = await store.createManualLead()
    if (created != null) {
      await loadLeads(true)
      selectedLeadId.value = created.id
    }
    message.success('Сделка открыта')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось открыть сделку')
  }
}

async function onCloseLead(statusId: number | null): Promise<void> {
  if (statusId == null || leadDetail.value == null) return
  try {
    await store.closeCurrentLead(statusId, leadDetail.value.id)
    await loadLeads(true)
    const created = await store.createManualLead()
    if (created != null) {
      await loadLeads(true)
      selectedLeadId.value = created.id
    }
    message.success('Сделка закрыта, открыта новая')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось закрыть сделку')
  }
}

async function saveLeadComment(): Promise<void> {
  const text = commentDraft.value.trim()
  if (!text || !hasSelectedOpenLead.value || leadDetail.value == null) return
  try {
    const updated = await patchLead(leadDetail.value.id, { comment: text })
    setCachedLeadDetail(updated)
    applyLeadDetail(updated)
    message.success('Комментарий добавлен')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка комментария')
  }
}
</script>

<template>
  <section class="deal-side">
    <header class="deal-side__header">
      <h2 class="deal-side__title">Сделки</h2>
      <NButton
        size="small"
        type="primary"
        :loading="store.creatingLead"
        :disabled="!chat || chat.assigned_group_id == null"
        @click="onCreateLead"
      >
        Новая сделка
      </NButton>
    </header>

    <div class="deal-side__scroll">
      <NSpin :show="(loadingLeads || loadingLead) && leadItems.length === 0 && leadDetail == null" class="deal-side__spin">
        <div v-if="!chat" class="deal-side__empty">Выберите чат</div>

        <div v-else-if="chat.assigned_group_id == null" class="deal-side__empty">
          Нужна группа у бота
        </div>

        <div v-else class="deal-side__body">
        <div v-if="leadItems.length > 0" class="deal-side__field">
          <span class="deal-side__label">Сделка</span>
          <NSelect
            v-model:value="selectedLeadId"
            size="small"
            :options="leadOptions"
            :consistent-menu-width="false"
          />
        </div>

        <div v-if="leadItems.length === 0" class="deal-side__empty">
          <p>Сделок пока нет</p>
        </div>

        <template v-if="leadDetail">
          <div class="deal-side__number-line">
            <span>Сделка №{{ leadDetail.id }}</span>
            <NTag size="small" :type="leadDetail.closed_at ? 'default' : 'success'" :bordered="false">
              {{ leadDetail.closed_at ? 'закрыта' : 'открыта' }}
            </NTag>
          </div>

          <div v-if="hasSelectedOpenLead" class="deal-side__field">
            <span class="deal-side__label">Статус</span>
            <NSelect
              v-model:value="selectedLeadStatusId"
              size="small"
              :options="leadStatusOptions"
              :consistent-menu-width="false"
              placeholder="Статус"
            />
          </div>

          <div v-if="hasSelectedOpenLead" class="deal-side__field">
            <span class="deal-side__label">Услуга</span>
            <NSelect
              v-model:value="service"
              size="small"
              :disabled="!hasSelectedOpenLead"
              :options="serviceOptions"
              placeholder="Выберите услугу"
              @update:value="persistOrderFields"
            />
          </div>

          <div v-if="hasSelectedOpenLead && isOptService" class="deal-side__field">
            <span class="deal-side__label">Период *</span>
            <NSelect
              v-model:value="period"
              size="small"
              :disabled="!hasSelectedOpenLead"
              :options="periodOptions"
              placeholder="Выберите период"
              @update:value="persistOrderFields"
            />
          </div>

          <OptOrdersPanel
            v-if="isOptService && leadDetail"
            :lead-id="leadDetail.id"
            :disabled="!hasSelectedOpenLead || !period"
            @payments-changed="refreshOptPaymentGate(leadDetail.id)"
          />

          <template v-if="isTreesService">
            <div class="deal-side__field deal-side__field--stacked">
              <span class="deal-side__label">Позиции</span>
              <div class="deal-side__tree-rows">
                <div v-for="line in treeLines" :key="line.id" class="deal-side__tree-row">
                  <div class="deal-side__tree-row-main">
                    <div class="deal-side__field deal-side__field--stacked">
                      <span class="deal-side__label">Тип</span>
                      <NSelect
                        :value="line.type || null"
                        :options="treeTypeOptions"
                        filterable
                        size="small"
                        placeholder="Тип услуги"
                        :disabled="!hasSelectedOpenLead"
                        @update:value="(v) => onTreeTypeChange(line.id, String(v || ''))"
                      />
                    </div>
                    <div class="deal-side__tree-row-nums">
                      <div class="deal-side__field deal-side__field--stacked">
                        <span class="deal-side__label">Цена за ед., ₽</span>
                        <NInputNumber
                          :value="line.unit_price ?? null"
                          size="small"
                          class="deal-side__number"
                          :show-button="false"
                          :disabled="!hasSelectedOpenLead"
                          :min="0"
                          placeholder="0"
                          @update:value="(v) => patchTreeLine(line.id, { unit_price: v })"
                        />
                      </div>
                      <div class="deal-side__field deal-side__field--stacked">
                        <span class="deal-side__label">Кол-во</span>
                        <NInputNumber
                          :value="line.quantity ?? null"
                          size="small"
                          class="deal-side__number"
                          :show-button="false"
                          :disabled="!hasSelectedOpenLead"
                          :min="0"
                          placeholder="0"
                          @update:value="(v) => patchTreeLine(line.id, { quantity: v })"
                        />
                      </div>
                    </div>
                    <div class="deal-side__tree-row-sum">
                      <span class="deal-side__label">Сумма</span>
                      <strong>{{ formatMoney(treeLineTotal(line)) }} ₽</strong>
                    </div>
                  </div>
                  <NButton
                    v-if="hasSelectedOpenLead"
                    size="tiny"
                    quaternary
                    type="error"
                    class="deal-side__tree-row-remove"
                    @click="removeTreeLine(line.id)"
                  >
                    <template #icon><Trash2 :size="14" /></template>
                  </NButton>
                </div>
              </div>
              <NButton
                v-if="hasSelectedOpenLead"
                size="small"
                secondary
                block
                style="margin-top: 8px"
                @click="addTreeLine"
              >
                <template #icon><Plus :size="14" /></template>
                Добавить позицию
              </NButton>
            </div>

            <div v-if="treeLines.length" class="deal-side__tree-adj">
              <span class="deal-side__label">Скидка / надбавка</span>
              <NRadioGroup
                :value="treeAdjDirection"
                :disabled="!hasSelectedOpenLead"
                @update:value="onTreeAdjDirection"
              >
                <NSpace>
                  <NRadio value="decrease">Скидка (−)</NRadio>
                  <NRadio value="increase">Надбавка (+)</NRadio>
                </NSpace>
              </NRadioGroup>
              <NInputNumber
                :value="treeAdjAmount"
                size="small"
                class="deal-side__number"
                :show-button="false"
                :disabled="!hasSelectedOpenLead"
                :min="0"
                placeholder="0"
                style="margin-top: 6px"
                @update:value="onTreeAdjAmount"
              />
              <p class="deal-side__hint">
                База {{ formatMoney(treeBaseTotal) }} ₽
                <template v-if="treeSignedAdjustment">
                  · корректировка {{ treeSignedAdjustment > 0 ? '+' : '' }}{{ formatMoney(treeSignedAdjustment) }} ₽
                </template>
              </p>
            </div>

            <dl v-if="treeLines.length" class="deal-side__pay-facts">
              <div>
                <dt>К оплате</dt>
                <dd>{{ formatMoney(treeDueTotal) }} ₽</dd>
              </div>
              <div>
                <dt>Оплачено</dt>
                <dd>{{ formatMoney(treeAmountPaid) }} ₽</dd>
              </div>
              <div>
                <dt>Остаток</dt>
                <dd>{{ formatMoney(treeAmountRemaining) }} ₽</dd>
              </div>
              <div>
                <dt>Оплата</dt>
                <dd>
                  <span :class="paymentStatusClass(treePayStatus)">
                    {{ optPaymentStatusLabel(treePayStatus) }}
                  </span>
                </dd>
              </div>
            </dl>

            <ul v-if="treePayments.length" class="deal-side__pay-list">
              <li v-for="pay in treePayments" :key="pay.id">
                {{ formatMoney(pay.amount) }} ₽ ·
                {{ optPaymentTypeLabel(pay.payment_type) }} ·
                {{ new Date(pay.paid_at).toLocaleString('ru-RU') }}
              </li>
            </ul>

            <NSpace vertical v-if="hasSelectedOpenLead">
              <NButton
                type="primary"
                secondary
                block
                size="small"
                :loading="savingFields"
                @click="persistOrderFields"
              >
                Сохранить
              </NButton>
              <NButton
                type="primary"
                block
                size="small"
                :disabled="!treeLines.length"
                @click="openTreePaymentModal"
              >
                Записать оплату
              </NButton>
            </NSpace>
          </template>

          <template v-else-if="!isOptService">
          <div class="deal-side__field deal-side__field--stacked">
            <span class="deal-side__label">Количество</span>
            <NInputNumber
              v-model:value="quantity"
              size="small"
              class="deal-side__number"
              :show-button="false"
              :disabled="!hasSelectedOpenLead"
              :min="0"
              @update:value="markOrderFormDirty"
              @blur="persistOrderFields"
            />
          </div>

          <div class="deal-side__field deal-side__field--stacked">
            <span class="deal-side__label">Стоимость</span>
            <NInputNumber
              v-model:value="cost"
              size="small"
              class="deal-side__number"
              :show-button="false"
              :disabled="!hasSelectedOpenLead"
              :min="0"
              @update:value="markOrderFormDirty"
              @blur="persistOrderFields"
            />
          </div>

          <div class="deal-side__field deal-side__field--stacked">
            <span class="deal-side__label">Себестоимость</span>
            <NInputNumber
              v-model:value="costPrice"
              size="small"
              class="deal-side__number"
              :show-button="false"
              :disabled="!hasSelectedOpenLead"
              :min="0"
              placeholder="Необязательно"
              @update:value="markOrderFormDirty"
              @blur="persistOrderFields"
            />
          </div>
          </template>

          <div v-if="hasSelectedOpenLead" class="deal-side__field deal-side__field--stacked">
            <div class="deal-side__value">
            <NSpace vertical>
              <NTooltip trigger="hover" :disabled="!closeWonTooltip">
                <template #trigger>
                  <span class="deal-side__btn-wrap">
                    <NButton
                      size="small"
                      type="success"
                      block
                      :disabled="wonStatusId == null || !canCloseWon"
                      :loading="store.closingLead"
                      @click="onCloseLead(wonStatusId)"
                    >
                      Успешная продажа
                    </NButton>
                  </span>
                </template>
                {{ closeWonTooltip }}
              </NTooltip>
              <NButton
                size="small"
                type="error"
                block
                :disabled="lostStatusId == null"
                :loading="store.closingLead"
                @click="onCloseLead(lostStatusId)"
              >
                Неуспешная продажа
              </NButton>
            </NSpace>
            </div>
          </div>

          <div v-if="leadDetail" class="deal-side__field deal-side__field--stacked">
            <span class="deal-side__label">Комментарии</span>
            <div class="deal-side__value">
              <div v-if="leadComments.length" class="deal-side__comments">
                <div
                  v-for="item in leadComments.slice(-3)"
                  :key="item.id"
                  class="deal-side__comment"
                >
                  <p>{{ item.body }}</p>
                  <span>{{ new Date(item.created_at).toLocaleString('ru-RU') }}</span>
                </div>
                <NButton
                  v-if="leadComments.length > 3"
                  size="tiny"
                  quaternary
                  @click="commentsOpen = true"
                >
                  Все комментарии ({{ leadComments.length }})
                </NButton>
              </div>
              <p v-else class="deal-side__hint">Комментариев пока нет</p>
              <template v-if="hasSelectedOpenLead">
                <NInput
                  v-model:value="commentDraft"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                  placeholder="Новый комментарий..."
                  @keydown.ctrl.enter.prevent="saveLeadComment"
                />
                <NSpace>
                  <NButton size="small" quaternary :loading="savingFields" @click="saveLeadComment">
                    Добавить комментарий
                  </NButton>
                  <NButton
                    v-if="leadComments.length"
                    size="small"
                    quaternary
                    @click="commentsOpen = true"
                  >
                    Открыть все
                  </NButton>
                </NSpace>
              </template>
            </div>
          </div>
        </template>
      </div>
      </NSpin>
    </div>

    <NModal
      v-model:show="commentsOpen"
      preset="card"
      title="Комментарии к сделке"
      style="max-width: 480px"
    >
      <ul v-if="leadComments.length" class="deal-side__comments-modal">
        <li v-for="item in leadComments" :key="item.id">
          <p>{{ item.body }}</p>
          <span>{{ new Date(item.created_at).toLocaleString('ru-RU') }}</span>
        </li>
      </ul>
      <p v-else class="deal-side__hint">Комментариев пока нет</p>
    </NModal>

    <NModal
      v-model:show="paymentOpen"
      preset="card"
      title="Записать оплату"
      style="width: min(420px, 94vw)"
    >
      <NForm label-placement="top" size="small">
        <NFormItem label="Сумма оплаты">
          <NInputNumber
            v-model:value="paymentForm.amount"
            :min="1"
            :show-button="false"
            style="width: 100%"
          />
        </NFormItem>
        <NFormItem label="Когда оплачено">
          <NDatePicker v-model:value="paymentForm.paid_at" type="datetime" style="width: 100%" />
        </NFormItem>
        <NFormItem label="Тип оплаты">
          <NSelect v-model:value="paymentForm.payment_type" :options="OPT_PAYMENT_TYPE_OPTIONS" />
        </NFormItem>
        <NFormItem label="Кому">
          <NSelect
            v-model:value="paymentForm.recipient"
            :options="OPT_PAYMENT_RECIPIENT_OPTIONS"
          />
        </NFormItem>
      </NForm>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="paymentOpen = false">Отмена</NButton>
          <NButton type="primary" :loading="savingFields" @click="submitTreePayment">
            Сохранить оплату
          </NButton>
        </NSpace>
      </template>
    </NModal>
  </section>
</template>

<style scoped>
.deal-side {
  display: flex;
  flex-direction: column;
  flex: 1;
  height: 100%;
  min-height: 0;
  padding: 12px;
  overflow: hidden;
}

.deal-side__scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
  padding-bottom: 16px;
}

.deal-side__spin {
  display: block;
  min-height: min-content;
}

.deal-side__spin :deep(.n-spin-container),
.deal-side__spin :deep(.n-spin-content) {
  min-height: 0;
}

.deal-side__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
  margin-bottom: 12px;
}

.deal-side__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
}

.deal-side__body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.deal-side__number-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-weight: 700;
}

.deal-side__section {
  margin: 8px 0 0;
  font-size: 0.9rem;
  font-weight: 600;
}

.deal-side__field {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 6px 10px;
  align-items: center;
}

.deal-side__field--stacked {
  align-items: start;
  grid-template-columns: 1fr;
}

.deal-side__value {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.deal-side__value :deep(.n-button__content) {
  white-space: normal;
  line-height: 1.25;
}

.deal-side__btn-wrap {
  display: block;
  width: 100%;
}

.deal-side__label {
  font-size: 0.8rem;
  color: var(--app-text-muted);
  line-height: 1.2;
}

.deal-side__hint {
  margin: 6px 0 0;
  font-size: 0.75rem;
  color: var(--app-text-muted);
  line-height: 1.35;
}

.deal-side__empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  color: var(--app-text-muted);
  font-size: 0.9rem;
}

.deal-side__empty p {
  margin: 0;
}

.deal-side__comments {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.deal-side__tree-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.deal-side__tree-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
}

.deal-side__tree-row-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.deal-side__tree-row-nums {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 10px;
}

.deal-side__tree-row-sum {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 0.9rem;
}

.deal-side__tree-row-remove {
  margin-top: 18px;
  flex-shrink: 0;
}

.deal-side__tree-adj {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.deal-side__number {
  width: 100% !important;
}

.deal-side__number :deep(.n-input) {
  width: 100%;
}

.deal-side__pay-facts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
  margin: 0;
}

.deal-side__pay-facts dt {
  font-size: 0.72rem;
  color: var(--app-text-muted);
}

.deal-side__pay-facts dd {
  margin: 2px 0 0;
  font-size: 0.9rem;
  font-weight: 650;
}

.deal-side__pay-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 0.78rem;
  color: var(--app-text-muted);
}

.deal-side__pay-pill {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 700;
  color: #fff;
  background: #6b7280;
}

.deal-side__pay-pill--ok {
  background: #1a7f37;
}

.deal-side__pay-pill--warn {
  background: #9a6700;
}

.deal-side__pay-pill--danger {
  background: #cf222e;
}

.deal-side__comment {
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--app-border) 35%, transparent);
}

.deal-side__comment p {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.85rem;
}

.deal-side__comment span,
.deal-side__comments-modal span {
  display: block;
  margin-top: 4px;
  font-size: 0.72rem;
  color: var(--app-text-muted);
}

.deal-side__comments-modal {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 420px;
  overflow-y: auto;
}

.deal-side__comments-modal li {
  padding-bottom: 10px;
  border-bottom: 1px solid var(--app-border);
}

.deal-side__comments-modal p {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
