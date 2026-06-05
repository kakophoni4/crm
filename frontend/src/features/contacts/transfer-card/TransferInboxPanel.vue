<script setup lang="ts">
import { NButton, NCard, NEmpty, NSpace, NTag, NText, useMessage } from 'naive-ui'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { getRealtimeWS } from '@/shared/realtime/ws-client'

import type { ContactTransferRecord, ContactTransferState } from '@/entities/contact/types'
import {
  acceptContactTransfer,
  approveContactTransfer,
  cancelContactTransfer,
  declineContactTransfer,
  listContactTransfers,
  rejectContactTransfer,
} from '@/features/contacts/api'
import { AppError } from '@/shared/api/http'
import { playTransferInboxSound } from '@/shared/audio/transfer-inbox'
import { useAuthStore } from '@/shared/store/auth'

withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })

const message = useMessage()
const auth = useAuthStore()

const loading = ref(false)
const actionLoadingById = ref<Record<number, boolean>>({})
const items = ref<ContactTransferRecord[]>([])

const pendingSenior = computed(() =>
  items.value.filter((row) => row.state === 'pending_senior'),
)

const pendingRecipient = computed(() =>
  items.value.filter((row) => row.state === 'pending_recipient'),
)

async function loadInbox(): Promise<void> {
  loading.value = true
  try {
    const [seniorData, recipientData] = await Promise.all([
      listContactTransfers({ state: 'pending_senior' }),
      listContactTransfers({ state: 'pending_recipient' }),
    ])
    const byId = new Map<number, ContactTransferRecord>()
    for (const row of [...seniorData.items, ...recipientData.items]) {
      byId.set(row.id, row)
    }
    items.value = [...byId.values()].sort((a, b) => b.id - a.id)
  } catch (err) {
    const text = err instanceof AppError ? err.message : 'Не удалось загрузить inbox передач'
    message.error(text)
  } finally {
    loading.value = false
  }
}

function canApprove(row: ContactTransferRecord): boolean {
  return row.state === 'pending_senior' && (auth.user?.role === 'senior' || auth.user?.role === 'admin')
}

function canDecline(row: ContactTransferRecord): boolean {
  return canApprove(row)
}

function canAccept(row: ContactTransferRecord): boolean {
  return row.state === 'pending_recipient' && row.to_user_id === auth.user?.id
}

function canReject(row: ContactTransferRecord): boolean {
  return canAccept(row)
}

function canCancel(row: ContactTransferRecord): boolean {
  return (
    (row.state === 'pending_senior' || row.state === 'pending_recipient') &&
    row.requested_by === auth.user?.id
  )
}

function stateLabel(state: ContactTransferState): string {
  const map: Record<ContactTransferState, string> = {
    pending_senior: 'Ожидает согласования',
    pending_recipient: 'Ожидает принятия',
    accepted: 'Принято',
    declined_senior: 'Отклонено при согласовании',
    declined_recipient: 'Отклонено получателем',
    cancelled: 'Отменено',
    expired: 'Истекло',
    pending: 'Ожидает',
    approved: 'Одобрено',
  }
  return map[state]
}

function stateTagType(state: ContactTransferState): 'default' | 'warning' | 'success' | 'error' {
  if (state === 'pending_senior' || state === 'pending_recipient' || state === 'pending' || state === 'approved') {
    return 'warning'
  }
  if (state === 'accepted') return 'success'
  if (state === 'declined_senior' || state === 'declined_recipient' || state === 'cancelled' || state === 'expired') {
    return 'error'
  }
  return 'default'
}

const transferVersionConflictMessage =
  'Заявка изменилась, обновите inbox'

async function runAction(
  row: ContactTransferRecord,
  action: () => Promise<ContactTransferRecord>,
  okText: string,
): Promise<void> {
  actionLoadingById.value = { ...actionLoadingById.value, [row.id]: true }
  try {
    await action()
    message.success(okText)
    await loadInbox()
  } catch (err) {
    if (err instanceof AppError && err.status === 409) {
      message.warning(transferVersionConflictMessage)
      await loadInbox()
      return
    }
    const text = err instanceof AppError ? err.message : 'Операция передачи не выполнена'
    message.error(text)
  } finally {
    actionLoadingById.value = { ...actionLoadingById.value, [row.id]: false }
  }
}

const transferTopics = [
  'contact.transfer.requested',
  'contact.ownership.transferred',
  'transfer.senior_approved',
  'transfer.recipient_accepted',
  'transfer.cancelled',
] as const

let unsubscribers: (() => void)[] = []

onMounted(() => {
  void loadInbox()
  for (const topic of transferTopics) {
    unsubscribers.push(
      getRealtimeWS().onTopic(topic, () => {
        void playTransferInboxSound()
        void loadInbox()
      }),
    )
  }
})

onUnmounted(() => {
  unsubscribers.forEach((fn) => fn())
  unsubscribers = []
})
</script>

<template>
  <NCard
    size="small"
    :embedded="embedded"
    :title="embedded ? undefined : 'Передачи карточек'"
  >
    <NSpace vertical :size="12">
      <NSpace justify="space-between" align="center">
        <NTag type="warning" :bordered="false">
          Ожидает согласования: {{ pendingSenior.length }}
        </NTag>
        <NTag type="warning" :bordered="false">
          Ожидает принятия: {{ pendingRecipient.length }}
        </NTag>
        <NButton tertiary size="small" :loading="loading" @click="loadInbox">
          Обновить
        </NButton>
      </NSpace>

      <div v-if="items.length" class="transfer-inbox__list">
        <NCard
          v-for="row in items"
          :key="row.id"
          size="small"
          embedded
          class="transfer-inbox__item"
        >
          <NSpace vertical :size="8">
            <NSpace justify="space-between" align="center">
              <strong>
                {{ row.contact_name ?? `Контакт #${row.contact_id}` }}
                <NText depth="3" style="font-size: 0.8rem"> · группа #{{ row.group_id }}</NText>
              </strong>
              <NTag :type="stateTagType(row.state)" :bordered="false">
                {{ stateLabel(row.state) }}
              </NTag>
            </NSpace>
            <div class="transfer-inbox__meta">
              <span>От: {{ row.from_user_name ?? `#${row.from_user_id}` }}</span>
              <span>Кому: {{ row.to_user_name ?? `#${row.to_user_id}` }}</span>
            </div>
            <div v-if="row.comment" class="transfer-inbox__comment">{{ row.comment }}</div>
            <NSpace>
              <NButton
                v-if="canApprove(row)"
                size="tiny"
                type="primary"
                :loading="Boolean(actionLoadingById[row.id])"
                @click="
                  runAction(
                    row,
                    () => approveContactTransfer(row.id, row.version),
                    'Передача одобрена',
                  )
                "
              >
                Одобрить
              </NButton>
              <NButton
                v-if="canDecline(row)"
                size="tiny"
                :loading="Boolean(actionLoadingById[row.id])"
                @click="runAction(row, () => declineContactTransfer(row.id), 'Передача отклонена')"
              >
                Отклонить
              </NButton>
              <NButton
                v-if="canAccept(row)"
                size="tiny"
                type="primary"
                :loading="Boolean(actionLoadingById[row.id])"
                @click="
                  runAction(
                    row,
                    () => acceptContactTransfer(row.id, row.version),
                    'Передача принята',
                  )
                "
              >
                Принять
              </NButton>
              <NButton
                v-if="canReject(row)"
                size="tiny"
                :loading="Boolean(actionLoadingById[row.id])"
                @click="runAction(row, () => rejectContactTransfer(row.id), 'Передача отклонена получателем')"
              >
                Отказаться
              </NButton>
              <NButton
                v-if="canCancel(row)"
                size="tiny"
                type="error"
                :loading="Boolean(actionLoadingById[row.id])"
                @click="runAction(row, () => cancelContactTransfer(row.id), 'Передача отменена')"
              >
                Отменить
              </NButton>
            </NSpace>
          </NSpace>
        </NCard>
      </div>
      <NEmpty v-else :description="loading ? 'Загрузка…' : 'Нет активных передач'" />
    </NSpace>
  </NCard>
</template>

<style scoped>
.transfer-inbox__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.transfer-inbox__item {
  border-radius: 8px;
}

.transfer-inbox__meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 0.8rem;
  opacity: 0.75;
}

.transfer-inbox__comment {
  font-size: 0.85rem;
  opacity: 0.9;
}
</style>
