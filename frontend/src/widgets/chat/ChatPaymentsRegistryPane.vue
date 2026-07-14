<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import { NButton, NDataTable, NEmpty, NSelect, NSpin, NTag, useMessage } from 'naive-ui'
import { h, onMounted, ref, watch } from 'vue'

import { useChatsStore } from '@/features/chats/store'
import { listOptOrdersRegistry } from '@/features/leads/opt-api'
import type { OptOrderRegistryItem } from '@/features/leads/opt-types'
import { optPaymentStatusLabel } from '@/features/leads/opt-types'
import { AppError } from '@/shared/api/http'

const emit = defineEmits<{
  openChat: [chatId: number]
}>()

const store = useChatsStore()
const message = useMessage()

const loading = ref(false)
const items = ref<OptOrderRegistryItem[]>([])
const total = ref(0)
const paymentStatusFilter = ref<string | null>('unpaid,partial')

const paymentStatusOptions = [
  { label: 'Не оплачена / частично', value: 'unpaid,partial' },
  { label: 'Не оплачена', value: 'unpaid' },
  { label: 'Частично', value: 'partial' },
  { label: 'Оплачена', value: 'paid' },
  { label: 'Все', value: null },
]

function formatMoney(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

function paymentTagType(status: string): 'default' | 'success' | 'error' | 'warning' {
  if (status === 'paid') return 'success'
  if (status === 'partial') return 'warning'
  return 'error'
}

function clientLabel(row: OptOrderRegistryItem): string {
  return row.contact_name || row.buyer.name || `ИНН ${row.buyer.inn}`
}

async function loadItems(): Promise<void> {
  loading.value = true
  try {
    const data = await listOptOrdersRegistry({
      payment_status: paymentStatusFilter.value || undefined,
      open_only: paymentStatusFilter.value !== 'paid',
      limit: 100,
      offset: 0,
    })
    items.value = data.items
    total.value = data.total
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить оплаты')
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function openRow(row: OptOrderRegistryItem): void {
  if (row.chat_id == null) {
    message.warning('У заявки нет связанного чата')
    return
  }
  emit('openChat', row.chat_id)
}

const columns: DataTableColumns<OptOrderRegistryItem> = [
  {
    title: 'Клиент',
    key: 'contact',
    ellipsis: { tooltip: true },
    render: (row) => clientLabel(row),
  },
  {
    title: 'Остаток',
    key: 'remaining',
    width: 100,
    align: 'right',
    render: (row) => `${formatMoney(row.amount_remaining)} ₽`,
  },
  {
    title: 'Статус',
    key: 'payment_status',
    width: 110,
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: paymentTagType(row.payment_status), bordered: false },
        { default: () => optPaymentStatusLabel(row.payment_status) },
      ),
  },
  {
    title: '',
    key: 'actions',
    width: 72,
    render: (row) =>
      h(
        NButton,
        {
          size: 'tiny',
          quaternary: true,
          disabled: row.chat_id == null,
          onClick: () => openRow(row),
        },
        { default: () => 'Чат' },
      ),
  },
]

watch(
  () => store.optOrdersRefreshNonce,
  () => {
    void loadItems()
  },
)

watch(paymentStatusFilter, () => {
  void loadItems()
})

onMounted(() => {
  void loadItems()
})
</script>

<template>
  <section class="payments-registry">
    <header class="payments-registry__header">
      <h2 class="payments-registry__title">Все оплаты</h2>
      <p class="payments-registry__subtitle">Реестр заявок ОПТ · {{ total }} шт.</p>
      <NSelect
        v-model:value="paymentStatusFilter"
        class="payments-registry__filter"
        size="small"
        :options="paymentStatusOptions"
        :clearable="false"
      />
    </header>

    <NSpin :show="loading">
      <NDataTable
        v-if="items.length"
        size="small"
        :columns="columns"
        :data="items"
        :bordered="false"
        :single-line="false"
        :row-key="(row: OptOrderRegistryItem) => row.id"
      />
      <NEmpty v-else description="Нет заявок по фильтру" />
    </NSpin>
  </section>
</template>

<style scoped>
.payments-registry {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  flex: 1;
  padding: 0 4px 12px;
  overflow: auto;
}

.payments-registry__header {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 4px 4px 0;
}

.payments-registry__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 650;
}

.payments-registry__subtitle {
  margin: 0;
  color: var(--app-text-muted);
  font-size: 0.8rem;
}

.payments-registry__filter {
  width: 100%;
}
</style>
