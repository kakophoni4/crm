<script setup lang="ts">
import {
  NButton,
  NForm,
  NFormItem,
  NInputNumber,
  NSelect,
  NSpace,
  NSpin,
  NSwitch,
  useMessage,
} from 'naive-ui'
import type { SelectOption } from 'naive-ui'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { REASSIGN_STRATEGY_OPTIONS } from '@/entities/contact/types'
import type { EscalationSettings, ReassignStrategy } from '@/entities/contact/types'
import { listGroups } from '@/features/admin/api'
import { getEscalationSettings, patchEscalationSettings } from '@/features/contacts/api'
import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

const loading = ref(true)
const saving = ref(false)
const settings = ref<EscalationSettings | null>(null)

const activeGroupId = ref<number | null>(null)
const groupSelectOptions = ref<SelectOption[]>([])
const noGroupsInScope = ref(false)

const canEdit = computed(
  () => auth.user?.role === 'senior' || auth.user?.role === 'admin',
)

const form = ref({
  first_response_timeout_minutes: 15,
  new_contact_reassign_strategy: 'first_responder' as ReassignStrategy,
  notify_owner_on_inbound: true,
  notify_group_on_escalation: true,
})

const strategyOptions = REASSIGN_STRATEGY_OPTIONS

const showGroupPicker = computed(
  () =>
    canEdit.value &&
    activeGroupId.value == null &&
    groupSelectOptions.value.length > 1 &&
    !noGroupsInScope.value,
)

const selectedGroupLabel = computed(() => {
  const id = activeGroupId.value
  if (id == null) return null
  const opt = groupSelectOptions.value.find((o) => o.value === id)
  return typeof opt?.label === 'string' ? opt.label : null
})

function parseRouteGroupId(): number | null {
  const n = Number(route.query.group_id)
  return Number.isFinite(n) && n > 0 ? n : null
}

function syncForm(data: EscalationSettings): void {
  form.value = {
    first_response_timeout_minutes: data.first_response_timeout_minutes,
    new_contact_reassign_strategy: data.new_contact_reassign_strategy,
    notify_owner_on_inbound: data.notify_owner_on_inbound,
    notify_group_on_escalation: data.notify_group_on_escalation,
  }
}

async function loadGroupOptions(): Promise<void> {
  const deptParam =
    auth.user?.role === 'senior' && auth.user.department_id != null
      ? auth.user.department_id
      : undefined
  const items = await listGroups(deptParam)
  groupSelectOptions.value = items.map((g) => ({ label: g.name, value: g.id }))
  noGroupsInScope.value = items.length === 0
}

async function loadSettings(): Promise<void> {
  if (activeGroupId.value == null) {
    loading.value = false
    return
  }

  loading.value = true
  try {
    settings.value = await getEscalationSettings(activeGroupId.value)
    syncForm(settings.value)
  } catch (err) {
    const text = err instanceof AppError ? err.message : 'Не удалось загрузить настройки'
    message.error(text)
  } finally {
    loading.value = false
  }
}

async function saveSettings(): Promise<void> {
  if (activeGroupId.value == null) return
  saving.value = true
  try {
    settings.value = await patchEscalationSettings(activeGroupId.value, {
      first_response_timeout_minutes: form.value.first_response_timeout_minutes,
      new_contact_reassign_strategy: form.value.new_contact_reassign_strategy,
      notify_owner_on_inbound: form.value.notify_owner_on_inbound,
      notify_group_on_escalation: form.value.notify_group_on_escalation,
    })
    syncForm(settings.value)
    message.success('Настройки эскалации сохранены')
  } catch (err) {
    const text = err instanceof AppError ? err.message : 'Не удалось сохранить'
    message.error(text)
  } finally {
    saving.value = false
  }
}

async function onPickGroup(id: number | null): Promise<void> {
  if (id == null) return
  activeGroupId.value = id
  await router.replace({ query: { ...route.query, group_id: String(id) } })
  await loadSettings()
}

async function resolveActiveGroup(): Promise<void> {
  await loadGroupOptions()
  if (noGroupsInScope.value) {
    activeGroupId.value = null
    return
  }

  let gid = parseRouteGroupId() ?? auth.user?.group_id ?? null
  if (gid != null && !groupSelectOptions.value.some((o) => o.value === gid)) {
    gid = null
  }

  if (gid != null) {
    activeGroupId.value = gid
    if (parseRouteGroupId() == null) {
      await router.replace({ query: { ...route.query, group_id: String(gid) } })
    }
    return
  }

  if (groupSelectOptions.value.length === 1) {
    const only = groupSelectOptions.value[0].value as number
    activeGroupId.value = only
    await router.replace({ query: { ...route.query, group_id: String(only) } })
  }
}

onMounted(async () => {
  if (!canEdit.value) {
    void router.replace({ name: 'dashboard' })
    return
  }

  loading.value = true
  try {
    await resolveActiveGroup()
    await loadSettings()
  } catch (err) {
    const text = err instanceof AppError ? err.message : 'Не удалось загрузить список групп'
    message.error(text)
    loading.value = false
  }
})

watch(
  () => route.query.group_id,
  async () => {
    if (!canEdit.value) return
    const gid = parseRouteGroupId()
    if (gid == null || gid === activeGroupId.value) return
    if (!groupSelectOptions.value.some((o) => o.value === gid)) return
    activeGroupId.value = gid
    await loadSettings()
  },
)
</script>

<template>
  <section class="group-escalation">
    <header class="group-escalation__header">
      <h1>Эскалация группы</h1>
      <p v-if="activeGroupId != null && selectedGroupLabel" class="group-escalation__sub">
        Группа «{{ selectedGroupLabel }}»
      </p>
      <p v-else-if="activeGroupId != null" class="group-escalation__sub">
        Группа без отображаемого названия
      </p>
      <p v-else-if="noGroupsInScope" class="group-escalation__sub group-escalation__sub--warn">
        В вашем отделе нет групп. Создайте группу в разделе «Группы».
      </p>
      <p v-else-if="showGroupPicker" class="group-escalation__sub">
        Выберите группу, для которой настраивается эскалация.
      </p>
    </header>

    <div v-if="showGroupPicker" class="group-escalation__picker">
      <NFormItem label="Группа" label-placement="left">
        <NSelect
          :value="null"
          placeholder="Выберите группу"
          :options="groupSelectOptions"
          style="max-width: 360px"
          @update:value="(v) => onPickGroup(v as number)"
        />
      </NFormItem>
    </div>

    <NSpin :show="loading">
      <NForm
        v-if="activeGroupId != null && canEdit"
        label-placement="top"
        class="group-escalation__form"
      >
        <NFormItem
          label="Таймаут ответа владельца, мин"
          extra="Сколько минут ждать первого ответа владельца карточки на новое входящее от клиента. По истечении времени срабатывает эскалация (уведомление группы и, для «новых» контактов, возможное переназначение)."
        >
          <NInputNumber
            v-model:value="form.first_response_timeout_minutes"
            :min="1"
            :max="1440"
            style="width: 100%"
          />
        </NFormItem>
        <NFormItem
          label="Стратегия для нового контакта без ответа владельца"
          extra="Используется только если у контакта ещё не было исходящего ответа владельца в этой группе и сработал таймаут: кому назначить карточку дальше — первому, кто уже отвечал по этому контакту, или случайному доступному оператору из группы."
        >
          <NSelect v-model:value="form.new_contact_reassign_strategy" :options="strategyOptions" />
        </NFormItem>
        <NFormItem
          label="Пуш владельцу при новом входящем"
          extra="Личное уведомление текущему владельцу карточки, что по чату пришло новое сообщение от клиента."
        >
          <NSwitch v-model:value="form.notify_owner_on_inbound" />
        </NFormItem>
        <NFormItem
          label="Уведомлять группу при эскалации"
          extra="После таймаута без ответа владельца чат попадает в общую повестку группы (все операторы группы видят, что по карточке нужно отреагировать)."
        >
          <NSwitch v-model:value="form.notify_group_on_escalation" />
        </NFormItem>
        <NSpace>
          <NButton type="primary" :loading="saving" @click="saveSettings">Сохранить</NButton>
        </NSpace>
      </NForm>
    </NSpin>
  </section>
</template>

<style scoped>
.group-escalation__header {
  margin-bottom: 20px;
}

.group-escalation__header h1 {
  margin: 0 0 4px;
  font-size: 1.5rem;
}

.group-escalation__sub {
  margin: 0;
  opacity: 0.75;
}

.group-escalation__sub--warn {
  color: #d03050;
}

.group-escalation__picker {
  margin-bottom: 16px;
  max-width: 480px;
}

.group-escalation__form {
  max-width: 480px;
}
</style>
