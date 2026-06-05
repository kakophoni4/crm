<script setup lang="ts">
import { NButton, NModal, NSelect, NSpace, useMessage } from 'naive-ui'
import type { SelectOption } from 'naive-ui'
import { computed, ref, watch } from 'vue'

import { listUsers } from '@/features/admin/api'
import type { AdminUser } from '@/features/admin/api'
import { transferHintForRole } from '@/features/chats/transfer-hint'
import { requestContactTransfer } from '@/features/contacts/api'
import { ensureGroupDirectory, lookupGroupName } from '@/features/groups/directory'
import { useAuthStore } from '@/shared/store/auth'

const props = defineProps<{
  show: boolean
  contactId: number | null
  groupId: number | null
  contactName?: string | null
  groupName?: string | null
  /** Текущий владелец карточки в группе — ему передать нельзя. */
  cardOwnerUserId?: number | null
}>()

const emit = defineEmits<{
  'update:show': [value: boolean]
  transferred: []
}>()

const auth = useAuthStore()
const message = useMessage()

const toUserId = ref<number | null>(null)
const loading = ref(false)
const groupUsers = ref<AdminUser[]>([])
const loadingUsers = ref(false)
const resolvedGroupName = ref<string | null>(null)
const resolvingGroupName = ref(false)

const hint = computed(() => transferHintForRole(auth.user?.role))
const displayGroupName = computed(() => resolvedGroupName.value?.trim() || null)
const scopeLine = computed(() => {
  if (props.contactId == null || props.groupId == null) return ''
  const contact = props.contactName?.trim() || `Контакт #${props.contactId}`
  if (resolvingGroupName.value) return `${contact} → …`
  const group = displayGroupName.value
  return group ? `${contact} → ${group}` : contact
})
const excludedRecipientIds = computed(() => {
  const ids = new Set<number>()
  if (props.cardOwnerUserId != null) ids.add(props.cardOwnerUserId)
  const me = auth.user?.id
  if (me != null) ids.add(me)
  return ids
})

const eligibleUsers = computed(() =>
  groupUsers.value.filter((u) => !excludedRecipientIds.value.has(u.id)),
)

const userOptions = computed<SelectOption[]>(() =>
  eligibleUsers.value.map((u) => ({ label: u.full_name, value: u.id })),
)

const noRecipients = computed(
  () => !loadingUsers.value && props.groupId != null && eligibleUsers.value.length === 0,
)
const isCardOwner = computed(
  () =>
    props.cardOwnerUserId != null &&
    auth.user?.id != null &&
    props.cardOwnerUserId === auth.user.id,
)

const canAssignInGroup = computed(() => auth.isSenior || auth.isAdmin)

const canSubmit = computed(
  () =>
    (isCardOwner.value || canAssignInGroup.value) &&
    props.contactId != null &&
    props.groupId != null &&
    toUserId.value != null,
)

async function resolveGroupName(): Promise<void> {
  const fromProps = props.groupName?.trim()
  if (fromProps) {
    resolvedGroupName.value = fromProps
    return
  }
  if (props.groupId == null) {
    resolvedGroupName.value = null
    return
  }
  resolvingGroupName.value = true
  try {
    await ensureGroupDirectory()
    resolvedGroupName.value = lookupGroupName(props.groupId)
  } finally {
    resolvingGroupName.value = false
  }
}

async function loadGroupUsers(): Promise<void> {
  if (props.groupId == null) return
  loadingUsers.value = true
  try {
    groupUsers.value = await listUsers({ group_id: props.groupId })
  } catch {
    groupUsers.value = []
  } finally {
    loadingUsers.value = false
  }
}

watch(eligibleUsers, (users) => {
  if (toUserId.value != null && !users.some((u) => u.id === toUserId.value)) {
    toUserId.value = null
  }
})

watch(
  () => props.show,
  (visible) => {
    if (!visible) {
      toUserId.value = null
      resolvedGroupName.value = null
      return
    }
    void resolveGroupName()
    if (props.groupId != null) void loadGroupUsers()
  },
)

watch(
  () => [props.groupId, props.groupName] as const,
  () => {
    if (props.show) void resolveGroupName()
  },
)

async function submit(): Promise<void> {
  if (!isCardOwner.value && !canAssignInGroup.value) {
    message.warning('Передать можно только свою карточку')
    return
  }
  if (!canSubmit.value || props.contactId == null || props.groupId == null) {
    message.warning('Выберите получателя')
    return
  }
  loading.value = true
  try {
    await requestContactTransfer(props.contactId, props.groupId, {
      to_user_id: toUserId.value!,
      force: canAssignInGroup.value,
    })
    message.success(
      canAssignInGroup.value
        ? 'Карточка назначена выбранному сотруднику'
        : 'Запрос на передачу карточки отправлен',
    )
    emit('transferred')
    emit('update:show', false)
  } catch (err) {
    message.error(err instanceof Error ? err.message : 'Не удалось передать карточку')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <NModal
    :show="show"
    preset="card"
    title="Передать карточку"
    style="max-width: 420px"
    @update:show="emit('update:show', $event)"
  >
    <p class="transfer-card-dialog__hint">{{ hint }}</p>
    <p v-if="scopeLine" class="transfer-card-dialog__scope">{{ scopeLine }}</p>
    <NSpace vertical :size="12">
      <p v-if="noRecipients" class="transfer-card-dialog__empty">
        Нет других операторов в группе для передачи.
      </p>
      <NSelect
        v-else
        v-model:value="toUserId"
        :options="userOptions"
        :loading="loadingUsers"
        placeholder="Выберите коллегу"
        filterable
        clearable
      />
    </NSpace>
    <template #footer>
      <NSpace justify="end">
        <NButton @click="emit('update:show', false)">Отмена</NButton>
        <NButton type="primary" :loading="loading" :disabled="!canSubmit" @click="submit">
          Передать карточку
        </NButton>
      </NSpace>
    </template>
  </NModal>
</template>

<style scoped>
.transfer-card-dialog__hint {
  margin: 0 0 8px;
  font-size: 0.9rem;
  opacity: 0.85;
}

.transfer-card-dialog__scope {
  margin: 0 0 12px;
  font-size: 0.8rem;
  opacity: 0.7;
}

.transfer-card-dialog__empty {
  margin: 0;
  font-size: 0.85rem;
  opacity: 0.75;
}
</style>
