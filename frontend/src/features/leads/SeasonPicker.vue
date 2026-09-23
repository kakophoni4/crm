<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { NSelect, NButton, NModal, NInput, NDatePicker, NSpace, useMessage } from 'naive-ui'
import { http, AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'
type Season = { id: number; name: string; starts_at: string; is_current: boolean; is_planned: boolean }
const props = defineProps<{ modelValue: number | null }>()
const emit = defineEmits<{ 'update:modelValue': [number | null]; ready: [] }>()
const auth = useAuthStore()
const message = useMessage()
const seasons = ref<Season[]>([])
const show = ref(false)
const busy = ref(false)
const name = ref('')
const start = ref<number | null>(null)
const failed = ref(false)
const options = computed(() => [
  { label: 'Все сезоны', value: 0 },
  ...seasons.value.map(s => ({label: `${s.name}${s.is_current ? ' · текущий' : s.is_planned ? ' · запланирован' : ' · прошлый'}`, value:s.id})),
])
let refreshTimer: ReturnType<typeof setInterval> | undefined
async function load() {
  try {
    const previousCurrent = seasons.value.find(s => s.is_current)?.id
    seasons.value = (await http.get<Season[]>('/sales-seasons')).data
    const current = seasons.value.find(s => s.is_current)?.id
    if (previousCurrent != null && props.modelValue === previousCurrent && current !== previousCurrent) emit('update:modelValue', current ?? 0)
    failed.value = false
    if (props.modelValue == null) emit('update:modelValue', seasons.value.find(s => s.is_current)?.id ?? 0)
    emit('ready')
  } catch { failed.value = true; message.error('Не удалось загрузить сезоны') }
}
async function save() {
  if (!name.value.trim() || start.value == null) { message.warning('Укажите название и дату начала'); return }
  busy.value = true
  try {
    await http.post('/sales-seasons', {name:name.value.trim(), starts_at:new Date(start.value).toISOString()})
    show.value = false
    await load()
    message.success('Сезон запланирован. Старые заявки сохранят свой сезон.')
  } catch (e) { message.error(e instanceof AppError ? e.message : 'Не удалось создать сезон') }
  finally { busy.value = false }
}
onMounted(() => { void load(); refreshTimer = setInterval(() => { void load() }, 60000) })
onUnmounted(() => clearInterval(refreshTimer))
</script>
<template>
  <NSpace align="center" wrap>
    <span style="font-size:12px;color:var(--app-text-muted)">Сезон</span>
    <NSelect size="small" style="width: min(290px, 70vw)" :value="modelValue ?? 0" :options="options" @update:value="emit('update:modelValue', $event)" />
    <NButton v-if="failed" @click="load">Повторить</NButton>
    <NButton size="small" quaternary v-if="auth.isAdmin" @click="show = true; start = Date.now() + 300000">+ Сезон</NButton>
  </NSpace>
  <NModal v-model:show="show" preset="card" title="Новый рабочий сезон" style="width: min(520px, 94vw)">
    <NSpace vertical>
      <NInput v-model:value="name" placeholder="Например: 3-й квартал 2026" maxlength="100" />
      <label>Дата и время начала ({{ Intl.DateTimeFormat().resolvedOptions().timeZone }})</label>
      <NDatePicker v-model:value="start" type="datetime" />
      <p>С этого момента новые заявки получат новый сезон. Все существующие заявки, их отчётные периоды, сделки и оплаты останутся на месте. Предыдущий сезон будет доступен в списке прошлых.</p>
      <NButton type="primary" :loading="busy" @click="save">Запланировать начало</NButton>
    </NSpace>
  </NModal>
</template>
