<script setup lang="ts">
import {
  NButton,
  NForm,
  NFormItem,
  NInput,
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

import type { AfterHoursSettings, WorkingHoursSchedule } from '@/entities/contact/types'
import { listGroups } from '@/features/admin/api'
import { getAfterHoursSettings, patchAfterHoursSettings } from '@/features/contacts/api'
import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'

const WEEKDAYS: { key: string; label: string }[] = [
  { key: 'mon', label: 'Пн' },
  { key: 'tue', label: 'Вт' },
  { key: 'wed', label: 'Ср' },
  { key: 'thu', label: 'Чт' },
  { key: 'fri', label: 'Пт' },
  { key: 'sat', label: 'Сб' },
  { key: 'sun', label: 'Вс' },
]

const TIMEZONE_OPTIONS: SelectOption[] = [
  { label: 'Europe/Moscow', value: 'Europe/Moscow' },
  { label: 'Europe/Kaliningrad', value: 'Europe/Kaliningrad' },
  { label: 'Europe/Samara', value: 'Europe/Samara' },
  { label: 'Asia/Yekaterinburg', value: 'Asia/Yekaterinburg' },
  { label: 'Asia/Novosibirsk', value: 'Asia/Novosibirsk' },
  { label: 'Asia/Krasnoyarsk', value: 'Asia/Krasnoyarsk' },
  { label: 'Asia/Irkutsk', value: 'Asia/Irkutsk' },
  { label: 'Asia/Vladivostok', value: 'Asia/Vladivostok' },
  { label: 'UTC', value: 'UTC' },
]

const route = useRoute()
const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

const loading = ref(true)
const saving = ref(false)
const settings = ref<AfterHoursSettings | null>(null)

const activeGroupId = ref<number | null>(null)
const groupSelectOptions = ref<SelectOption[]>([])
const noGroupsInScope = ref(false)

const canEdit = computed(
  () => auth.user?.role === 'senior' || auth.user?.role === 'group_senior' || auth.user?.role === 'admin',
)

type DayHours = { enabled: boolean; start: string; end: string }

const form = ref({
  enabled: false,
  reply_text: '',
  delay_minutes: 15,
  timezone: 'Europe/Moscow',
  cooldown_minutes: 120,
  days: Object.fromEntries(
    WEEKDAYS.map((d) => [d.key, { enabled: d.key !== 'sat' && d.key !== 'sun', start: '09:00', end: '18:00' }]),
  ) as Record<string, DayHours>,
})

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

function scheduleFromForm(): WorkingHoursSchedule {
  const out: WorkingHoursSchedule = {}
  for (const { key } of WEEKDAYS) {
    const day = form.value.days[key]
    out[key] = day?.enabled ? [[day.start || '09:00', day.end || '18:00']] : []
  }
  return out
}

function syncForm(data: AfterHoursSettings): void {
  const days: Record<string, DayHours> = {}
  for (const { key } of WEEKDAYS) {
    const windows = data.working_hours?.[key] ?? []
    const first = Array.isArray(windows) && windows.length > 0 ? windows[0] : null
    days[key] = {
      enabled: Boolean(first),
      start: first?.[0] ?? '09:00',
      end: first?.[1] ?? '18:00',
    }
  }
  form.value = {
    enabled: data.enabled,
    reply_text: data.reply_text ?? '',
    delay_minutes: data.delay_minutes,
    timezone: data.timezone || 'Europe/Moscow',
    cooldown_minutes: data.cooldown_minutes,
    days,
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
    settings.value = await getAfterHoursSettings(activeGroupId.value)
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
  if (form.value.enabled && !form.value.reply_text.trim()) {
    message.warning('Укажите текст автоответа')
    return
  }
  saving.value = true
  try {
    settings.value = await patchAfterHoursSettings(activeGroupId.value, {
      enabled: form.value.enabled,
      reply_text: form.value.reply_text,
      delay_minutes: form.value.delay_minutes,
      timezone: form.value.timezone,
      cooldown_minutes: form.value.cooldown_minutes,
      working_hours: scheduleFromForm(),
    })
    syncForm(settings.value)
    message.success('Настройки автоответа сохранены')
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
  <section class="after-hours">
    <header class="after-hours__header">
      <h1>Автоответ вне рабочего времени</h1>
      <p v-if="activeGroupId != null && selectedGroupLabel" class="after-hours__sub">
        Группа «{{ selectedGroupLabel }}»
      </p>
      <p v-else-if="activeGroupId != null" class="after-hours__sub">
        Группа без отображаемого названия
      </p>
      <p v-else-if="noGroupsInScope" class="after-hours__sub after-hours__sub--warn">
        В вашем отделе нет групп. Создайте группу в разделе «Группы».
      </p>
      <p v-else-if="showGroupPicker" class="after-hours__sub">
        Выберите группу, для которой настраивается автоответ.
      </p>
      <p v-else class="after-hours__sub">
        Если клиент пишет вне рабочих часов и оператор не ответил за указанное время — бот отправит текст автоответа.
      </p>
    </header>

    <div v-if="showGroupPicker" class="after-hours__picker">
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
        class="after-hours__form"
      >
        <NFormItem label="Включить автоответ" extra="Работает только вне настроенных рабочих часов.">
          <NSwitch v-model:value="form.enabled" />
        </NFormItem>
        <NFormItem
          label="Текст автоответа"
          extra="Сообщение клиенту от имени бота, если оператор не ответил вовремя."
        >
          <NInput
            v-model:value="form.reply_text"
            type="textarea"
            :rows="4"
            placeholder="Сейчас вне рабочего времени. Мы ответим в ближайшее рабочее время."
          />
        </NFormItem>
        <NFormItem
          label="Задержка без ответа, мин"
          extra="Сколько минут ждать ответа оператора после входящего сообщения клиента, прежде чем отправить автоответ."
        >
          <NInputNumber v-model:value="form.delay_minutes" :min="1" :max="1440" style="width: 100%" />
        </NFormItem>
        <NFormItem
          label="Пауза между автоответами, мин"
          extra="Минимальный интервал между автоответами одному контакту (чтобы не спамить при серии сообщений)."
        >
          <NInputNumber
            v-model:value="form.cooldown_minutes"
            :min="0"
            :max="10080"
            style="width: 100%"
          />
        </NFormItem>
        <NFormItem label="Часовой пояс">
          <NSelect
            v-model:value="form.timezone"
            :options="TIMEZONE_OPTIONS"
            filterable
            tag
          />
        </NFormItem>
        <NFormItem
          label="Рабочие часы"
          extra="В эти интервалы автоответ не отправляется. Пустой день = выходной."
        >
          <div class="after-hours__days">
            <div v-for="day in WEEKDAYS" :key="day.key" class="after-hours__day">
              <span class="after-hours__day-label">{{ day.label }}</span>
              <NSwitch v-model:value="form.days[day.key].enabled" size="small" />
              <NInput
                v-model:value="form.days[day.key].start"
                :disabled="!form.days[day.key].enabled"
                placeholder="09:00"
                style="width: 88px"
              />
              <span class="after-hours__dash">—</span>
              <NInput
                v-model:value="form.days[day.key].end"
                :disabled="!form.days[day.key].enabled"
                placeholder="18:00"
                style="width: 88px"
              />
            </div>
          </div>
        </NFormItem>
        <NSpace>
          <NButton type="primary" :loading="saving" @click="saveSettings">Сохранить</NButton>
        </NSpace>
      </NForm>
    </NSpin>
  </section>
</template>

<style scoped>
.after-hours__header {
  margin-bottom: 16px;
}

.after-hours__header h1 {
  margin: 0 0 4px;
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.after-hours__sub {
  margin: 0;
  color: var(--app-text-muted);
}

.after-hours__sub--warn {
  color: var(--app-danger);
}

.after-hours__picker {
  margin-bottom: 16px;
  max-width: 480px;
}

.after-hours__form {
  max-width: 560px;
}

.after-hours__days {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.after-hours__day {
  display: flex;
  align-items: center;
  gap: 10px;
}

.after-hours__day-label {
  width: 28px;
  font-weight: 600;
}

.after-hours__dash {
  color: var(--app-text-muted);
}
</style>
