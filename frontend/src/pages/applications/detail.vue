<script setup lang="ts">
import { NButton, useMessage } from 'naive-ui'
import { ArrowLeft, MessageSquare } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import type { OptOrder } from '@/features/leads/opt-types'
import OptOrdersPanel from '@/widgets/chat/OptOrdersPanel.vue'

const props = defineProps<{
  leadId: number
  orderId: number
}>()

const router = useRouter()
const route = useRoute()
const message = useMessage()
const selected = ref<OptOrder | null>(null)

const title = computed(() => {
  const orderNo = selected.value?.order_no ?? props.orderId
  const kind = selected.value?.order_kind === 'benik' ? 'Беник' : 'заявка'
  return `Сделка №${props.leadId} · ${kind} №${orderNo}`
})

const chatId = computed(() => {
  const raw = route.query.chat
  const n = Number(Array.isArray(raw) ? raw[0] : raw)
  return Number.isFinite(n) && n > 0 ? n : null
})

const listQuery = computed(() => {
  const tab = route.query.tab
  return tab === 'benik' || tab === 'payments' ? { tab: String(tab) } : undefined
})

function goBack(): void {
  void router.push({ name: 'applications', query: listQuery.value })
}

function goToChat(): void {
  if (chatId.value == null) {
    message.warning('У заявки нет связанного чата')
    return
  }
  void router.push({ name: 'chats', query: { chatId: String(chatId.value) } })
}

function onSelect(order: OptOrder): void {
  selected.value = order
  if (order.id === props.orderId) return
  void router.replace({
    name: 'application-detail',
    params: { leadId: String(props.leadId), orderId: String(order.id) },
    query: route.query,
  })
}
</script>

<template>
  <div class="application-detail">
    <header class="application-detail__header">
      <div class="application-detail__title-row">
        <NButton quaternary size="small" @click="goBack">
          <template #icon><ArrowLeft :size="16" /></template>
          К заявкам
        </NButton>
        <h1>{{ title }}</h1>
      </div>
      <NButton type="primary" size="small" :disabled="chatId == null" @click="goToChat">
        <template #icon><MessageSquare :size="16" /></template>
        Перейти в чат
      </NButton>
    </header>

    <p v-if="selected" class="application-detail__meta">
      <span>{{ selected.buyer.name || `ИНН ${selected.buyer.inn}` }}</span>
      <span v-if="selected.source_filename"> · {{ selected.source_filename }}</span>
    </p>

    <OptOrdersPanel
      class="application-detail__panel"
      layout="page"
      :lead-id="leadId"
      :initial-order-id="orderId"
      @select="onSelect"
    />
  </div>
</template>

<style scoped>
.application-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  min-height: 0;
  min-width: 0;
  width: 100%;
  padding: 16px 20px 16px;
  box-sizing: border-box;
  overflow: hidden;
}

.application-detail__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  flex-shrink: 0;
}

.application-detail__title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.application-detail__title-row h1 {
  margin: 0;
  font-size: 1.15rem;
  font-weight: 700;
  line-height: 1.3;
}

.application-detail__meta {
  margin: 0;
  flex-shrink: 0;
  font-size: 0.82rem;
  color: var(--app-text-muted);
}

.application-detail__panel {
  flex: 1 1 auto;
  min-height: 0;
}
</style>
