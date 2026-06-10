<script setup lang="ts">
import { NButton, NInput, NInputNumber, NSelect, NSpace, NSpin, useMessage } from 'naive-ui'
import type { SelectOption } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import type { ChatDetail } from '@/entities/chat/types'
import { getLead } from '@/features/leads/api'
import {
  buildLeadDealPatch,
  mergeServiceSuggestion,
  readLeadDealFields,
} from '@/features/leads/order-fields'
import type { LeadDetail } from '@/features/leads/types'
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

const leadDetail = ref<LeadDetail | null>(null)
const loadingLead = ref(false)
const savingFields = ref(false)

const openLeadId = computed(() => props.chat?.current_lead?.id ?? null)
const hasOpenLead = computed(
  () => props.chat?.current_lead != null && props.chat.current_lead.closed_at == null,
)

const dealNumber = ref('')
const service = ref('')
const quantity = ref<number | null>(null)
const cost = ref<number | null>(null)
const costPrice = ref<number | null>(null)
const commentDraft = ref('')

const serviceOptions = computed<SelectOption[]>(() => {
  const fields = readLeadDealFields(leadDetail.value?.custom_fields)
  return (fields.service_suggestions ?? []).map((name) => ({ label: name, value: name }))
})

const displayDealNumber = computed(() => {
  const custom = dealNumber.value.trim()
  if (custom) return custom
  if (openLeadId.value != null) return String(openLeadId.value)
  return '—'
})

async function loadLeadDetail(leadId: number): Promise<void> {
  loadingLead.value = true
  try {
    leadDetail.value = await getLead(leadId)
    const fields = readLeadDealFields(leadDetail.value.custom_fields)
    dealNumber.value = fields.deal_number ?? ''
    service.value = fields.order?.service?.toString() ?? ''
    const qty = fields.order?.quantity
    quantity.value = qty == null || qty === '' ? null : Number(qty)
    const costRaw = fields.order?.cost
    cost.value = costRaw == null || costRaw === '' ? null : Number(costRaw)
    const cpRaw = fields.order?.cost_price
    costPrice.value = cpRaw == null || cpRaw === '' ? null : Number(cpRaw)
    commentDraft.value = ''
  } catch {
    leadDetail.value = null
  } finally {
    loadingLead.value = false
  }
}

watch(
  openLeadId,
  (id) => {
    if (id == null) {
      leadDetail.value = null
      return
    }
    void loadLeadDetail(id)
  },
  { immediate: true },
)

async function persistOrderFields(): Promise<void> {
  if (!hasOpenLead.value || leadDetail.value == null) return
  savingFields.value = true
  try {
    let customFields = buildLeadDealPatch(leadDetail.value.custom_fields, {
      deal_number: dealNumber.value.trim() || null,
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
    await store.updateCurrentLeadCustomFields(customFields)
    leadDetail.value = {
      ...leadDetail.value,
      custom_fields: customFields,
    }
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить сделку')
  } finally {
    savingFields.value = false
  }
}

async function onCreateLead(): Promise<void> {
  try {
    await store.createManualLead()
    message.success('Сделка открыта')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось открыть сделку')
  }
}

async function onCloseLead(statusId: number | null): Promise<void> {
  if (statusId == null) return
  try {
    await store.closeCurrentLead(statusId)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось закрыть сделку')
  }
}

async function saveLeadComment(): Promise<void> {
  const text = commentDraft.value.trim()
  if (!text) return
  try {
    await store.updateCurrentLeadComment(text)
    commentDraft.value = ''
    if (openLeadId.value != null) {
      await loadLeadDetail(openLeadId.value)
    }
    message.success('Комментарий добавлен')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Ошибка комментария')
  }
}
</script>

<template>
  <section class="deal-side">
    <header class="deal-side__header">
      <h2 class="deal-side__title">Сделка</h2>
      <p v-if="hasOpenLead" class="deal-side__subtitle">№ {{ displayDealNumber }}</p>
    </header>

    <NSpin :show="loadingLead">
      <div v-if="!chat" class="deal-side__empty">Выберите чат</div>

      <div v-else-if="!hasOpenLead" class="deal-side__empty">
        <p>Нет открытой сделки</p>
        <NButton
          type="primary"
          size="small"
          :loading="store.creatingLead"
          :disabled="chat.assigned_group_id == null"
          @click="onCreateLead"
        >
          Новая сделка
        </NButton>
        <p v-if="chat.assigned_group_id == null" class="deal-side__hint">
          Нужна группа у бота
        </p>
      </div>

      <div v-else class="deal-side__body">
        <div class="deal-side__field">
          <span class="deal-side__label">Номер сделки</span>
          <NInput
            v-model:value="dealNumber"
            size="small"
            placeholder="Авто или свой номер"
            @blur="persistOrderFields"
          />
        </div>

        <h3 class="deal-side__section">Заказ</h3>

        <div class="deal-side__field">
          <span class="deal-side__label">1. Услуга</span>
          <NSelect
            v-model:value="service"
            size="small"
            filterable
            tag
            :options="serviceOptions"
            placeholder="Введите услугу"
            @update:value="persistOrderFields"
          />
        </div>

        <div class="deal-side__field">
          <span class="deal-side__label">2. Количество</span>
          <NInputNumber
            v-model:value="quantity"
            size="small"
            class="deal-side__number"
            :min="0"
            @blur="persistOrderFields"
          />
        </div>

        <div class="deal-side__field">
          <span class="deal-side__label">3. Стоимость</span>
          <NInputNumber
            v-model:value="cost"
            size="small"
            class="deal-side__number"
            :min="0"
            @blur="persistOrderFields"
          />
        </div>

        <div class="deal-side__field">
          <span class="deal-side__label">4. Себестоимость</span>
          <NInputNumber
            v-model:value="costPrice"
            size="small"
            class="deal-side__number"
            :min="0"
            placeholder="Необязательно"
            @blur="persistOrderFields"
          />
        </div>

        <div class="deal-side__field">
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

        <div class="deal-side__field">
          <span class="deal-side__label">Комментарий к сделке</span>
          <NInput
            v-model:value="commentDraft"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            placeholder="Новый комментарий…"
            @keydown.ctrl.enter.prevent="saveLeadComment"
          />
          <NButton size="small" quaternary :loading="savingFields" @click="saveLeadComment">
            Добавить комментарий
          </NButton>
        </div>
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
  flex-shrink: 0;
  margin-bottom: 12px;
}

.deal-side__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
}

.deal-side__subtitle {
  margin: 4px 0 0;
  font-size: 0.85rem;
  color: var(--app-text-muted);
}

.deal-side__body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  min-height: 0;
  flex: 1;
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

.deal-side__hint {
  margin: 0;
  font-size: 0.75rem;
}
</style>
