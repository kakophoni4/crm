<script setup lang="ts">
import { NModal, NSpin, NTag } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { getLead } from '@/features/leads/api'
import { readLeadDealFields } from '@/features/leads/order-fields'
import type { LeadDetail } from '@/features/leads/types'
import { leadCommentItems } from '@/features/leads/comments'
import { formatLeadDate, formatLeadOpenState, leadListItemLabel } from '@/features/leads/mapping'

const props = defineProps<{
  show: boolean
  leadId: number | null
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
}>()

const lead = ref<LeadDetail | null>(null)
const loading = ref(false)

const orderFields = computed(() => readLeadDealFields(lead.value?.custom_fields))

const comments = computed(() => (lead.value ? leadCommentItems(lead.value) : []))

watch(
  () => [props.show, props.leadId] as const,
  ([visible, leadId]) => {
    if (!visible || leadId == null) {
      lead.value = null
      return
    }
    void load(leadId)
  },
)

async function load(leadId: number): Promise<void> {
  loading.value = true
  try {
    lead.value = await getLead(leadId)
  } catch {
    lead.value = null
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
    style="width: min(520px, 96vw)"
    @update:show="emit('update:show', $event)"
  >
    <NSpin :show="loading">
      <div v-if="lead" class="lead-deal-modal">
        <div class="lead-deal-modal__meta">
          <NTag size="small">{{ lead.status_label ?? '—' }}</NTag>
          <span>{{ formatLeadOpenState(lead.closed_at) }}</span>
          <span v-if="lead.created_at" class="lead-deal-modal__date">
            {{ formatLeadDate(lead.created_at) }}
          </span>
        </div>

        <p v-if="leadListItemLabel(lead) !== '—'" class="lead-deal-modal__status-line">
          {{ leadListItemLabel(lead) }}
        </p>

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

        <div v-if="comments.length" class="lead-deal-modal__comments">
          <h4>Комментарии</h4>
          <ul>
            <li v-for="item in comments" :key="item.id">
              <p>{{ item.body }}</p>
              <span>{{ formatLeadDate(item.created_at) }}</span>
            </li>
          </ul>
        </div>

        <p v-else-if="lead.comment" class="lead-deal-modal__comment">{{ lead.comment }}</p>
      </div>
    </NSpin>
  </NModal>
</template>

<style scoped>
.lead-deal-modal {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.lead-deal-modal__meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 0.85rem;
}

.lead-deal-modal__date {
  color: var(--app-text-muted);
}

.lead-deal-modal__status-line {
  margin: 0;
  font-size: 0.9rem;
  color: var(--app-text-muted);
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

.lead-deal-modal__comments h4 {
  margin: 0 0 8px;
  font-size: 0.85rem;
}

.lead-deal-modal__comments ul {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lead-deal-modal__comments p {
  margin: 0 0 2px;
  white-space: pre-wrap;
}

.lead-deal-modal__comments span {
  font-size: 0.8rem;
  color: var(--app-text-muted);
}
</style>
