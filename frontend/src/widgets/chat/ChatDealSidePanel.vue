<script setup lang="ts">
import {
  NButton,
  NInput,
  NInputNumber,
  NSelect,
  NSpace,
  NSpin,
  NTag,
  useMessage,
} from 'naive-ui'
import type { SelectOption } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import type { ChatDetail } from '@/entities/chat/types'
import { getLead, listContactLeads, patchLead } from '@/features/leads/api'
import {
  buildLeadDealPatch,
  mergeServiceSuggestion,
  readLeadDealFields,
} from '@/features/leads/order-fields'
import type { LeadDetail, LeadListItem } from '@/features/leads/types'
import { useChatsStore } from '@/features/chats/store'
import { AppError } from '@/shared/api/http'

const props = defineProps<{
  chat: ChatDetail | null
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

const serviceOptions = computed<SelectOption[]>(() => {
  const fields = readLeadDealFields(leadDetail.value?.custom_fields)
  return (fields.service_suggestions ?? []).map((name) => ({ label: name, value: name }))
})

const leadOptions = computed<SelectOption[]>(() =>
  leadItems.value.map((lead) => ({
    label: `Сделка №${lead.id}`,
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

async function loadLeadDetail(leadId: number): Promise<void> {
  loadingLead.value = true
  try {
    applyLeadDetail(await getLead(leadId))
  } catch {
    leadDetail.value = null
    resetOrderForm()
  } finally {
    loadingLead.value = false
  }
}

async function loadLeads(): Promise<void> {
  const chat = props.chat
  if (chat == null) {
    leadItems.value = []
    leadDetail.value = null
    resetOrderForm()
    return
  }
  loadingLeads.value = true
  try {
    const data = await listContactLeads(chat.contact_id, {
      group_id: chat.assigned_group_id ?? undefined,
      limit: 100,
    })
    const items = data.items.filter((lead) => lead.chat_id === chat.id)
    leadItems.value = items
    const preferredId =
      selectedLeadId.value != null && items.some((lead) => lead.id === selectedLeadId.value)
        ? selectedLeadId.value
        : (items.find((lead) => lead.closed_at == null)?.id ?? items[0]?.id ?? null)
    await store.selectLead(preferredId)
  } catch {
    leadItems.value = []
  } finally {
    loadingLeads.value = false
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

async function persistOrderFields(): Promise<void> {
  if (!hasSelectedOpenLead.value || leadDetail.value == null) return
  savingFields.value = true
  try {
    let customFields = buildLeadDealPatch(leadDetail.value.custom_fields, {
      order: {
        service: service.value.trim() || undefined,
        quantity: quantity.value ?? undefined,
        cost: cost.value ?? undefined,
        cost_price: costPrice.value ?? undefined,
      },
    })
    if (service.value.trim()) {
      customFields = mergeServiceSuggestion(customFields, service.value)
    }
    const updated = await patchLead(leadDetail.value.id, { custom_fields: customFields })
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
    applyLeadDetail(updated)
    await loadLeads()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось изменить статус')
  }
}

async function onCreateLead(): Promise<void> {
  try {
    const created = await store.createManualLead()
    if (created != null) {
      await loadLeads()
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
    await loadLeads()
    message.success('Сделка закрыта')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось закрыть сделку')
  }
}

async function saveLeadComment(): Promise<void> {
  const text = commentDraft.value.trim()
  if (!text || !hasSelectedOpenLead.value || leadDetail.value == null) return
  try {
    const updated = await patchLead(leadDetail.value.id, { comment: text })
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

    <NSpin :show="loadingLeads || loadingLead">
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

        <div v-if="leadItems.length > 0" class="deal-side__lead-list">
          <button
            v-for="lead in leadItems"
            :key="lead.id"
            type="button"
            class="deal-side__lead-chip"
            :class="{ 'deal-side__lead-chip--active': lead.id === selectedLeadId }"
            @click="selectedLeadId = lead.id"
          >
            <span>№{{ lead.id }}</span>
            <NTag size="tiny" :type="lead.closed_at ? 'default' : 'success'" :bordered="false">
              {{ statusLabel(lead) }}
            </NTag>
          </button>
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

          <h3 class="deal-side__section">Заказ</h3>

          <div class="deal-side__field">
            <span class="deal-side__label">Услуга</span>
            <NSelect
              v-model:value="service"
              size="small"
              filterable
              tag
              :disabled="!hasSelectedOpenLead"
              :options="serviceOptions"
              placeholder="Введите услугу"
              @update:value="persistOrderFields"
            />
          </div>

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

          <div v-if="hasSelectedOpenLead" class="deal-side__field">
            <span class="deal-side__label">Завершить сделку</span>
            <NSpace vertical>
              <NButton
                size="small"
                type="success"
                block
                :disabled="wonStatusId == null"
                :loading="store.closingLead"
                @click="onCloseLead(wonStatusId)"
              >
                Успешная продажа
              </NButton>
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

          <div v-if="hasSelectedOpenLead" class="deal-side__field">
            <span class="deal-side__label">Комментарий к сделке</span>
            <NInput
              v-model:value="commentDraft"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              placeholder="Новый комментарий..."
              @keydown.ctrl.enter.prevent="saveLeadComment"
            />
            <NButton size="small" quaternary :loading="savingFields" @click="saveLeadComment">
              Добавить комментарий
            </NButton>
          </div>
        </template>
      </div>
    </NSpin>
  </section>
</template>

<style scoped>
.deal-side {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 12px;
  overflow: hidden;
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
  overflow-y: auto;
  min-height: 0;
  flex: 1;
}

.deal-side__lead-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.deal-side__lead-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 7px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  background: transparent;
  color: var(--app-text);
  cursor: pointer;
}

.deal-side__lead-chip--active {
  border-color: var(--app-accent, #2080f0);
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
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.deal-side__label {
  font-size: 0.8rem;
  color: var(--app-text-muted);
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
</style>
