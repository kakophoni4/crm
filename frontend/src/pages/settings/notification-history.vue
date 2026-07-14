<script setup lang="ts">
import { NButton, NSelect, NSpace, NSpin, NTag, useMessage } from 'naive-ui'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  getNotificationHistory,
  type StaffNotificationEvent,
} from '@/features/notifications/api'
import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'

const KIND_LABEL: Record<string, string> = {
  inbound_message: 'Сообщение',
  new_card: 'Новая карточка',
  escalation_group_senior: 'Эскалация → старший группы',
  escalation_dept_senior: 'Эскалация → старший отдела',
  escalation_admin: 'Эскалация → админ',
}

const STATUS_TYPE: Record<string, 'success' | 'warning' | 'error' | 'default' | 'info'> = {
  sent: 'warning',
  acked: 'success',
  cancelled: 'default',
  failed: 'error',
}

const STATUS_LABEL: Record<string, string> = {
  sent: 'Не ознакомлен',
  acked: 'Прочитано',
  cancelled: 'Отменено (ответ)',
  failed: 'Ошибка',
}

const message = useMessage()
const router = useRouter()
const auth = useAuthStore()

const loading = ref(true)
const loadingMore = ref(false)
const items = ref<StaffNotificationEvent[]>([])
const nextCursor = ref<number | null>(null)
const statusFilter = ref<string | null>(null)

const statusOptions = [
  { label: 'Все', value: null },
  { label: 'Не ознакомлен', value: 'sent' },
  { label: 'Прочитано', value: 'acked' },
  { label: 'Отменено', value: 'cancelled' },
  { label: 'Ошибка', value: 'failed' },
]

function fmt(iso: string | null): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ru-RU')
  } catch {
    return iso
  }
}

async function load(reset = true): Promise<void> {
  if (reset) {
    loading.value = true
    items.value = []
    nextCursor.value = null
  } else {
    loadingMore.value = true
  }
  try {
    const data = await getNotificationHistory({
      cursor: reset ? undefined : (nextCursor.value ?? undefined),
      limit: 40,
      status: statusFilter.value ?? undefined,
    })
    items.value = reset ? data.items : [...items.value, ...data.items]
    nextCursor.value = data.next_cursor
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить историю')
  } finally {
    loading.value = false
    loadingMore.value = false
  }
}

onMounted(() => {
  const role = auth.user?.role
  if (role !== 'admin' && role !== 'senior') {
    void router.replace({ name: 'notifications' })
    return
  }
  void load()
})
</script>

<template>
  <section class="hist">
    <header class="hist__header">
      <div>
        <h1>История уведомлений</h1>
        <p class="hist__sub">Кому ушло уведомление и ознакомился ли получатель</p>
      </div>
      <NSpace>
        <NSelect
          v-model:value="statusFilter"
          :options="statusOptions"
          style="width: 180px"
          @update:value="() => load(true)"
        />
        <NButton @click="router.push({ name: 'notifications' })">К настройкам</NButton>
      </NSpace>
    </header>

    <NSpin :show="loading">
      <div v-if="!items.length && !loading" class="hist__empty">Пока нет записей</div>
      <div v-else class="hist__list">
        <article v-for="row in items" :key="row.id" class="hist__row">
          <div class="hist__row-top">
            <NTag :type="STATUS_TYPE[row.status] || 'default'" size="small">
              {{ STATUS_LABEL[row.status] || row.status }}
            </NTag>
            <span class="hist__kind">{{ KIND_LABEL[row.kind] || row.kind }}</span>
            <span class="hist__time">{{ fmt(row.created_at) }}</span>
          </div>
          <div class="hist__main">
            <div>
              <b>{{ row.target_user_name || `user #${row.target_user_id}` }}</b>
              <span v-if="row.telegram_user_id" class="hist__muted"> · TG {{ row.telegram_user_id }}</span>
            </div>
            <div v-if="row.contact_name">Контакт: {{ row.contact_name }}</div>
            <div v-if="row.acked_at" class="hist__ok">Ознакомился: {{ fmt(row.acked_at) }}</div>
            <div v-else-if="row.cancelled_at" class="hist__muted">
              Отменено после ответа: {{ fmt(row.cancelled_at) }}
            </div>
            <div v-else-if="row.status === 'sent'" class="hist__warn">Ещё не ознакомился</div>
          </div>
        </article>
      </div>
      <div v-if="nextCursor" class="hist__more">
        <NButton :loading="loadingMore" @click="load(false)">Ещё</NButton>
      </div>
    </NSpin>
  </section>
</template>

<style scoped>
.hist__header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.hist__header h1 {
  margin: 0 0 4px;
  font-size: 1.5rem;
  font-weight: 700;
}
.hist__sub,
.hist__muted,
.hist__time {
  color: var(--app-text-muted);
}
.hist__list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.hist__row {
  border: 1px solid var(--app-border, #e5e7eb);
  border-radius: 10px;
  padding: 12px 14px;
  background: var(--app-surface, transparent);
}
.hist__row-top {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.hist__kind {
  font-weight: 600;
}
.hist__time {
  margin-left: auto;
  font-size: 0.85rem;
}
.hist__ok {
  color: var(--app-success, #16a34a);
}
.hist__warn {
  color: var(--app-warning, #ca8a04);
}
.hist__empty,
.hist__more {
  margin-top: 12px;
}
</style>
