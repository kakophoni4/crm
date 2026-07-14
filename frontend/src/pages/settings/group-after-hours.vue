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
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

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

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

const loading = ref(true)
const saving = ref(false)
const groupIds = ref<number[]>([])
const noGroupsInScope = ref(false)

/** Старший отдела или админ — единый автоответчик на весь отдел/скоуп. */
const canEdit = computed(() => auth.user?.role === 'senior' || auth.user?.role === 'admin')

type DayHours = { enabled: boolean; start: string; end: string }

const form = ref({
  enabled: false,
  reply_text: '',
  delay_minutes: 15,
  timezone: 'Europe/Moscow',
  cooldown_minutes: 120,
  days: Object.fromEntries(
    WEEKDAYS.map((d) => [
      d.key,
      { enabled: d.key !== 'sat' && d.key !== 'sun', start: '09:00', end: '18:00' },
    ]),
  ) as Record<string, DayHours>,
})

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

async function resolveGroups(): Promise<void> {
  const deptParam =
    auth.user?.role === 'senior' && auth.user.department_id != null
      ? auth.user.department_id
      : undefined
  const items = await listGroups(deptParam)
  groupIds.value = items.map((g) => g.id)
  noGroupsInScope.value = items.length === 0
}

async function loadSettings(): Promise<void> {
  if (!groupIds.value.length) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    // Одна форма на весь отдел: читаем с первой группы как шаблон.
    const data = await getAfterHoursSettings(groupIds.value[0])
    syncForm(data)
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить настройки')
  } finally {
    loading.value = false
  }
}

async function saveSettings(): Promise<void> {
  if (!groupIds.value.length) return
  if (form.value.enabled && !form.value.reply_text.trim()) {
    message.warning('Укажите текст автоответа')
    return
  }
  saving.value = true
  const body = {
    enabled: form.value.enabled,
    reply_text: form.value.reply_text,
    delay_minutes: form.value.delay_minutes,
    timezone: form.value.timezone,
    cooldown_minutes: form.value.cooldown_minutes,
    working_hours: scheduleFromForm(),
  }
  try {
    // Пишем одинаковые настройки во все группы отдела — автоответчик единый.
    let last: AfterHoursSettings | null = null
    for (const gid of groupIds.value) {
      last = await patchAfterHoursSettings(gid, body)
    }
    if (last) syncForm(last)
    message.success('Сохранено')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  if (!canEdit.value) {
    void router.replace({ name: 'dashboard' })
    return
  }
  loading.value = true
  try {
    await resolveGroups()
    await loadSettings()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить')
    loading.value = false
  }
})
</script>

<template>
  <section class="after-hours">
    <header class="after-hours__header">
      <h1>Автоответчик в нерабочее время</h1>
      <p v-if="noGroupsInScope" class="after-hours__sub after-hours__sub--warn">
        В отделе нет групп. Создайте группу в разделе «Группы».
      </p>
    </header>

    <NSpin :show="loading">
      <NForm v-if="groupIds.length && canEdit" label-placement="top" class="after-hours__form">
        <NFormItem label="Включён">
          <NSwitch v-model:value="form.enabled" />
        </NFormItem>
        <NFormItem label="Текст">
          <NInput
            v-model:value="form.reply_text"
            type="textarea"
            :rows="4"
            placeholder="Сейчас вне рабочего времени. Мы ответим в ближайшее рабочее время."
          />
        </NFormItem>
        <NFormItem label="Задержка без ответа, мин">
          <NInputNumber v-model:value="form.delay_minutes" :min="1" :max="1440" style="width: 100%" />
        </NFormItem>
        <NFormItem label="Пауза между ответами, мин">
          <NInputNumber
            v-model:value="form.cooldown_minutes"
            :min="0"
            :max="10080"
            style="width: 100%"
          />
        </NFormItem>
        <NFormItem label="Часовой пояс">
          <NSelect v-model:value="form.timezone" :options="TIMEZONE_OPTIONS" filterable tag />
        </NFormItem>
        <NFormItem label="Рабочие часы">
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
  font-size: 1.35rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.25;
}

.after-hours__sub {
  margin: 0;
  color: var(--app-text-muted);
}

.after-hours__sub--warn {
  color: var(--app-danger);
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
