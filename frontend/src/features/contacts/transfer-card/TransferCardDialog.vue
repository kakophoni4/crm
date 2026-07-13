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
  groupOptions?: SelectOption[]
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
const selectedGroupId = ref<number | null>(props.groupId)
const loading = ref(false)
const groupUsers = ref<AdminUser[]>([])
const loadingUsers = ref(false)
const resolvedGroupName = ref<string | null>(null)
const resolvingGroupName = ref(false)

const hint = computed(() => transferHintForRole(auth.user?.role))
const canAssignInGroup = computed(() => auth.canForceCardOwner)
const groupOptions = computed<SelectOption[]>(() => {
  const options = props.groupOptions ?? []
  if (options.length > 0) return options
  if (props.groupId == null) return []
  return [
    {
      label: props.groupName?.trim() || lookupGroupName(props.groupId) || `#${props.groupId}`,
      value: props.groupId,
    },
  ]
})
const showGroupSelect = computed(() => canAssignInGroup.value && groupOptions.value.length > 1)
const displayGroupName = computed(() => {
  const option = groupOptions.value.find((item) => item.value === selectedGroupId.value)
  const label = typeof option?.label === 'string' ? option.label.trim() : ''
  return label || resolvedGroupName.value?.trim() || null
})
const scopeLine = computed(() => {
  if (props.contactId == null || selectedGroupId.value == null) return ''
  const contact = props.contactName?.trim() || `Контакт #${props.contactId}`
  if (resolvingGroupName.value) return `${contact} → …`
  const group = displayGroupName.value
  return group ? `${contact} → ${group}` : contact
})
const excludedRecipientIds = computed(() => {
  const ids = new Set<number>()
  if (props.cardOwnerUserId != null) ids.add(props.cardOwnerUserId)
  if (!canAssignInGroup.value) {
    const me = auth.user?.id
    if (me != null) ids.add(me)
  }
  return ids
})

const eligibleUsers = computed(() =>
  groupUsers.value.filter((u) => !excludedRecipientIds.value.has(u.id)),
)

const userOptions = computed<SelectOption[]>(() =>
  eligibleUsers.value.map((u) => ({ label: u.full_name, value: u.id })),
)

const noRecipients = computed(
  () => !loadingUsers.value && selectedGroupId.value != null && eligibleUsers.value.length === 0,
)
const isCardOwner = computed(
  () =>
    props.cardOwnerUserId != null &&
    auth.user?.id != null &&
    props.cardOwnerUserId === auth.user.id,
)

const canSubmit = computed(
  () =>
    (isCardOwner.value || canAssignInGroup.value) &&
    props.contactId != null &&
    props.groupId != null &&
    selectedGroupId.value != null &&
    toUserId.value != null,
)

async function resolveGroupName(): Promise<void> {
  const fromOption = groupOptions.value.find((item) => item.value === selectedGroupId.value)
  if (typeof fromOption?.label === 'string' && fromOption.label.trim()) {
    resolvedGroupName.value = fromOption.label.trim()
    return
  }
  const fromProps = selectedGroupId.value === props.groupId ? props.groupName?.trim() : ''
  if (fromProps) {
    resolvedGroupName.value = fromProps
    return
  }
  if (selectedGroupId.value == null) {
    resolvedGroupName.value = null
    return
  }
  resolvingGroupName.value = true
  try {
    await ensureGroupDirectory()
    resolvedGroupName.value = lookupGroupName(selectedGroupId.value)
  } finally {
    resolvingGroupName.value = false
  }
}

async function loadGroupUsers(): Promise<void> {
  if (selectedGroupId.value == null) return
  loadingUsers.value = true
  try {
    groupUsers.value = await listUsers({ group_id: selectedGroupId.value })
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
      selectedGroupId.value = props.groupId
      resolvedGroupName.value = null
      return
    }
    selectedGroupId.value = props.groupId
    void resolveGroupName()
    if (selectedGroupId.value != null) void loadGroupUsers()
  },
)

watch(
  () => [props.groupId, props.groupName, props.groupOptions] as const,
  () => {
    if (selectedGroupId.value == null) selectedGroupId.value = props.groupId
    if (props.show) void resolveGroupName()
  },
)

watch(selectedGroupId, () => {
  toUserId.value = null
  if (!props.show) return
  void resolveGroupName()
  void loadGroupUsers()
})

async function submit(): Promise<void> {
  if (!isCardOwner.value && !canAssignInGroup.value) {
    message.warning('Передать можно только свою карточку')
    return
  }
  if (
    !canSubmit.value ||
    props.contactId == null ||
    props.groupId == null ||
    selectedGroupId.value == null
  ) {
    message.warning('Выберите получателя')
    return
  }
  loading.value = true
  try {
    await requestContactTransfer(props.contactId, props.groupId, {
      to_user_id: toUserId.value!,
      target_group_id:
        selectedGroupId.value !== props.groupId ? selectedGroupId.value : undefined,
      force: canAssignInGroup.value,
    })
    message.success('Карточка назначена выбранному сотруднику')
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
      <NSelect
        v-if="showGroupSelect"
        v-model:value="selectedGroupId"
        :options="groupOptions"
        placeholder="Группа"
        filterable
      />
      <p v-if="noRecipients" class="transfer-card-dialog__empty">
        Нет других операторов в группе для передачи.
      </p>
      <NSelect
        v-if="!noRecipients"
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
