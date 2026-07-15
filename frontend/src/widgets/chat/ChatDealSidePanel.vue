<script setup lang="ts">
import {
  NButton,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  NTooltip,
  useMessage,
} from 'naive-ui'
import type { SelectOption } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import type { ChatDetail } from '@/entities/chat/types'
import type { BotListItem } from '@/entities/bot/types'
import {
  getCachedLeadDetail,
  getChatDealsSnapshot,
  isChatDealsSnapshotFresh,
  pickPreferredLeadId,
  setCachedLeadDetail,
  setChatDealsSnapshot,
} from '@/features/chats/deals-cache'
import { getLead, listContactLeads, patchLead } from '@/features/leads/api'
import { listOptOrders } from '@/features/leads/opt-api'
import {
  buildLeadDealPatch,
  readLeadDealFields,
} from '@/features/leads/order-fields'
import { serviceOptionsForBot } from '@/features/leads/service-types'
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
const quantity = ref<number | null>(null)
const cost = ref<number | null>(null)
const costPrice = ref<number | null>(null)
const commentDraft = ref('')
const commentsOpen = ref(false)
const optPaymentsReady = ref(true)

const serviceOptions = computed<SelectOption[]>(() => {
  const botId = props.chat?.bot_id
  const bot = botId != null ? props.bots?.find((row) => row.id === botId) : null
  return serviceOptionsForBot(bot?.service_types, service.value)
})

const isOptService = computed(() => service.value === 'ОПТ')

const leadComments = computed(() =>
  leadDetail.value ? leadCommentItems(leadDetail.value) : [],
)

const canCloseWon = computed(
  () => hasSelectedOpenLead.value && (!isOptService.value || optPaymentsReady.value),
)

const closeWonTooltip = computed(() => {
  if (!hasSelectedOpenLead.value || props.wonStatusId == null) return null
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

function resetOrderForm(): void {
  service.value = ''
  quantity.value = null
  cost.value = null
  costPrice.value = null
  commentDraft.value = ''
}

function applyLeadDetail(detail: LeadDetail): void {
  leadDetail.value = detail
  const fields = readLeadDealFields(detail.custom_fields)
  service.value = fields.order?.service?.toString() ?? ''
  const qty = fields.order?.quantity
  quantity.value = qty == null || qty === '' ? null : Number(qty)
  const costRaw = fields.order?.cost
  cost.value = costRaw == null || costRaw === '' ? null : Number(costRaw)
  const cpRaw = fields.order?.cost_price
  costPrice.value = cpRaw == null || cpRaw === '' ? null : Number(cpRaw)
  commentDraft.value = ''
}

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

async function loadLeadDetail(leadId: number, forceRefresh = false): Promise<void> {
  if (!forceRefresh) {
    const cached = getCachedLeadDetail(leadId)
    if (cached) {
      applyLeadDetail(cached)
      await refreshOptPaymentGate(cached.id)
      return
    }
  }
  loadingLead.value = true
  try {
    const detail = await getLead(leadId)
    setCachedLeadDetail(detail)
    applyLeadDetail(detail)
    await refreshOptPaymentGate(detail.id)
  } catch {
    leadDetail.value = null
    resetOrderForm()
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
    if (!forceRefresh && isChatDealsSnapshotFresh(chat.id)) {
      await store.selectLead(preferredId)
      return
    }
  } else {
    // No cache for this chat — clear previous chat's deals immediately.
    leadItems.value = []
    leadDetail.value = null
    resetOrderForm()
  }

  loadingLeads.value = !cached
  try {
    const data = await listContactLeads(chat.contact_id, {
      group_id: chat.assigned_group_id ?? undefined,
      limit: 100,
    })
    // Chat may have changed while request was in flight.
    if (props.chat?.id !== chat.id) return
    const items = data.items.filter((lead) => lead.chat_id === chat.id)
    leadItems.value = items
    const preferredId =
      selectedLeadId.value != null && items.some((lead) => lead.id === selectedLeadId.value)
        ? selectedLeadId.value
        : pickPreferredLeadId(items)
    setChatDealsSnapshot(chat.id, items, preferredId)
    if (preferredId != null) {
      try {
        setCachedLeadDetail(await getLead(preferredId))
      } catch {
        /* detail load is optional here; loadLeadDetail will retry */
      }
    }
    if (props.chat?.id !== chat.id) return
    await store.selectLead(preferredId)
  } catch (err) {
    if (props.chat?.id === chat.id) {
      leadItems.value = []
      message.error(
        err instanceof AppError ? err.message : 'Не удалось загрузить сделки по контакту',
      )
    }
  } finally {
    if (props.chat?.id === chat.id) {
      loadingLeads.value = false
    }
  }
}

watch(
  () => [props.chat?.id, props.chat?.current_lead?.id] as const,
  () => {
    void loadLeads()
  },
  { immediate: true },
)

watch(
  selectedLeadId,
  (id) => {
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
    const customFields = buildLeadDealPatch(leadDetail.value.custom_fields, {
      order: {
        service: service.value.trim() || undefined,
        quantity: quantity.value ?? undefined,
        cost: cost.value ?? undefined,
        cost_price: costPrice.value ?? undefined,
      },
    })
    const updated = await patchLead(leadDetail.value.id, { custom_fields: customFields })
    setCachedLeadDetail(updated)
    applyLeadDetail(updated)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить сделку')
  } finally {
    savingFields.value = false
  }
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
      <NSpin :show="loadingLeads || loadingLead" class="deal-side__spin">
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

          <OptOrdersPanel
            v-if="isOptService && leadDetail"
            :lead-id="leadDetail.id"
            :disabled="!hasSelectedOpenLead"
            @payments-changed="refreshOptPaymentGate(leadDetail.id)"
          />

          <template v-if="!isOptService">
          <div class="deal-side__field">
            <span class="deal-side__label">Количество</span>
            <NInputNumber
              v-model:value="quantity"
              size="small"
              class="deal-side__number"
              :disabled="!hasSelectedOpenLead"
              :min="0"
              @blur="persistOrderFields"
            />
          </div>

          <div class="deal-side__field">
            <span class="deal-side__label">Стоимость</span>
            <NInputNumber
              v-model:value="cost"
              size="small"
              class="deal-side__number"
              :disabled="!hasSelectedOpenLead"
              :min="0"
              @blur="persistOrderFields"
            />
          </div>

          <div class="deal-side__field">
            <span class="deal-side__label">Себестоимость</span>
            <NInputNumber
              v-model:value="costPrice"
              size="small"
              class="deal-side__number"
              :disabled="!hasSelectedOpenLead"
              :min="0"
              placeholder="Необязательно"
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

.deal-side__number {
  width: 100%;
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
