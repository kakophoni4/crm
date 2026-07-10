<script setup lang="ts">
import { NEmpty, NSpin } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import type { ChatDetail } from '@/entities/chat/types'
import {
  getCachedLeadDetail,
  getChatDealsSnapshot,
} from '@/features/chats/deals-cache'
import { getLead, listContactLeads } from '@/features/leads/api'
import { readLeadDealFields } from '@/features/leads/order-fields'
import { useChatsStore } from '@/features/chats/store'
import OptOrdersPanel from '@/widgets/chat/OptOrdersPanel.vue'

const props = defineProps<{
  chat: ChatDetail | null
}>()

const store = useChatsStore()
const loading = ref(false)
const isOpt = ref(false)

const leadId = computed(() => store.selectedLeadId)
const hasOpenLead = computed(() => {
  if (leadId.value == null) return false
  const detail = getCachedLeadDetail(leadId.value)
  return detail != null && detail.closed_at == null
})

async function refreshLeadService(): Promise<void> {
  if (props.chat == null || leadId.value == null) {
    isOpt.value = false
    return
  }
  loading.value = true
  try {
    let detail = getCachedLeadDetail(leadId.value)
    if (detail == null) {
      detail = await getLead(leadId.value)
    }
    const fields = readLeadDealFields(detail.custom_fields)
    isOpt.value = fields.order?.service?.toString() === 'ОПТ'
  } catch {
    isOpt.value = false
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.chat?.id, leadId.value, store.optOrdersRefreshNonce] as const,
  () => {
    void refreshLeadService()
  },
  { immediate: true },
)

watch(
  () => props.chat?.id,
  async (chatId) => {
    if (chatId == null || props.chat?.contact_id == null) return
    if (store.selectedLeadId != null) return
    const snapshot = getChatDealsSnapshot(chatId)
    if (snapshot?.preferredLeadId != null) {
      await store.selectLead(snapshot.preferredLeadId)
      return
    }
    try {
      const leads = await listContactLeads(props.chat.contact_id, {
        group_id: props.chat.assigned_group_id ?? undefined,
        open_only: true,
        limit: 20,
      })
      const preferred = leads.items[0]?.id ?? null
      if (preferred != null) await store.selectLead(preferred)
    } catch {
      /* ignore */
    }
  },
  { immediate: true },
)
</script>

<template>
  <section class="payments-side">
    <header class="payments-side__header">
      <h2 class="payments-side__title">Оплаты</h2>
    </header>
    <div class="payments-side__scroll">
      <NSpin :show="loading">
        <div v-if="!chat" class="payments-side__empty">Выберите чат</div>
        <div v-else-if="leadId == null" class="payments-side__empty">
          Выберите сделку во вкладке «Сделки»
        </div>
        <template v-else-if="isOpt">
          <OptOrdersPanel
            :lead-id="leadId"
            :disabled="!hasOpenLead"
            @payments-changed="store.bumpOptOrdersRefresh()"
          />
        </template>
        <NEmpty
          v-else
          description="Оплаты доступны для сделок с услугой ОПТ"
        />
      </NSpin>
    </div>
  </section>
</template>

<style scoped>
.payments-side {
  display: flex;
  flex-direction: column;
  flex: 1;
  height: 100%;
  min-height: 0;
  padding: 12px;
  overflow: hidden;
}

.payments-side__header {
  flex-shrink: 0;
  margin-bottom: 12px;
}

.payments-side__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
}

.payments-side__scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior: contain;
  padding-bottom: 16px;
}

.payments-side__empty {
  color: var(--app-text-muted);
  font-size: 0.9rem;
}
</style>
