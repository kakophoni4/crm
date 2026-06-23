<script setup lang="ts">
import { NModal, NSpin, NTag } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { getLead } from '@/features/leads/api'
import { readLeadDealFields } from '@/features/leads/order-fields'
import type { LeadDetail } from '@/features/leads/types'
import * as chatsApi from '@/features/chats/api'
import type { ChatMessage } from '@/entities/chat/types'
import MessageList from '@/widgets/chat/MessageList.vue'

const props = defineProps<{
  show: boolean
  leadId: number | null
  chatId: number | null
  contactId?: number | null
  contactName?: string | null
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
}>()

const lead = ref<LeadDetail | null>(null)
const messages = ref<ChatMessage[]>([])
const loading = ref(false)

const orderFields = computed(() => readLeadDealFields(lead.value?.custom_fields))

watch(
  () => [props.show, props.leadId, props.chatId] as const,
  ([visible, leadId, chatId]) => {
    if (!visible || leadId == null || chatId == null) {
      lead.value = null
      messages.value = []
      return
    }
    void load(leadId, chatId)
  },
)

async function load(leadId: number, chatId: number): Promise<void> {
  loading.value = true
  try {
    const [leadRow, msgPage] = await Promise.all([
      getLead(leadId),
      chatsApi.listMessages(chatId, { lead_id: leadId, limit: 50 }),
    ])
    lead.value = leadRow
    messages.value = msgPage.items
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    :title="lead ? `Сделка № ${lead.id}` : 'Сделка'"
    style="width: min(720px, 96vw); max-height: 90vh"
    @update:show="emit('update:show', $event)"
  >
    <NSpin :show="loading">
      <div v-if="lead" class="lead-deal-modal">
        <div class="lead-deal-modal__meta">
          <NTag size="small">{{ lead.status_label ?? '—' }}</NTag>
          <span v-if="lead.closed_at">Закрыта</span>
          <span v-else>Открыта</span>
        </div>

        <dl class="lead-deal-modal__grid">
          <dt>Услуга</dt>
          <dd>{{ orderFields.order?.service || '—' }}</dd>
          <dt>Количество</dt>
          <dd>{{ orderFields.order?.quantity ?? '—' }}</dd>
          <dt>Стоимость</dt>
          <dd>{{ orderFields.order?.cost ?? '—' }}</dd>
          <dt>Себестоимость</dt>
          <dd>{{ orderFields.order?.cost_price ?? '—' }}</dd>
        </dl>

        <p v-if="lead.comment" class="lead-deal-modal__comment">{{ lead.comment }}</p>

        <div class="lead-deal-modal__chat">
          <h4>Переписка по сделке</h4>
          <MessageList
            :messages="messages"
            :chat-id="chatId"
            :contact-id="contactId"
            :contact-name="contactName"
            :has-more="false"
          />
        </div>
      </div>
    </NSpin>
  </NModal>
</template>

<style scoped>
.lead-deal-modal {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: calc(90vh - 120px);
}

.lead-deal-modal__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
}

.lead-deal-modal__grid {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 6px 12px;
  margin: 0;
  font-size: 0.9rem;
}

.lead-deal-modal__grid dt {
  color: var(--app-text-muted);
}

.lead-deal-modal__grid dd {
  margin: 0;
}

.lead-deal-modal__comment {
  margin: 0;
  white-space: pre-wrap;
  font-size: 0.9rem;
}

.lead-deal-modal__chat {
  display: flex;
  flex-direction: column;
  min-height: 240px;
  max-height: 360px;
  border: 1px solid var(--app-border);
  border-radius: 8px;
  overflow: hidden;
}

.lead-deal-modal__chat h4 {
  margin: 0;
  padding: 8px 12px;
  font-size: 0.85rem;
  border-bottom: 1px solid var(--app-border);
}
</style>
