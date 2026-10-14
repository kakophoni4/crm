<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  NAlert, NButton, NEmpty, NProgress, NTag, NUpload, useMessage,
  type UploadCustomRequestOptions,
} from 'naive-ui'
import { http, AppError } from '@/shared/api/http'
import AppCard from '@/shared/ui/AppCard.vue'

interface CheckJob {
  id: string
  filename: string
  status: string
  created_at: string
  updated_at: string
  total: number
  completed: number
  checks_done: number
  checks_total: number
  failed_checks: number
  rejected_rows: number
  duplicates: number
  input_rows: number
  progress: number
  current_inn: string | null
  source_label: string
  error: string | null
  result_ready: boolean
}

const message = useMessage()
const jobs = ref<CheckJob[]>([])
const uploading = ref(false)
const refreshing = ref(false)
const connectionError = ref('')
const busy = ref<Record<string, boolean>>({})
const activeStates = new Set(['queued', 'waiting', 'running', 'exporting'])
const labels: Record<string, string> = {
  queued: 'В очереди', waiting: 'Ожидает завершения текущего парсера',
  running: 'Проверяется', exporting: 'Собирается Excel', completed: 'Готово',
  completed_with_errors: 'Готово: часть источников недоступна',
  failed: 'Обработка прервана', cancelled: 'Остановлено',
}
const activeCount = computed(() => jobs.value.filter(j => activeStates.has(j.status)).length)
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false

function errorText(err: unknown, fallback: string): string {
  return err instanceof AppError ? err.message : fallback
}

async function refresh(): Promise<void> {
  if (refreshing.value || disposed) return
  refreshing.value = true
  try {
    const { data } = await http.get<{ items: CheckJob[] }>('/lavok-parser/checks', { timeout: 20000 })
    if (!disposed) jobs.value = data.items
    connectionError.value = ''
  } catch (err) {
    connectionError.value = errorText(err, 'Не удалось получить прогресс проверки')
  } finally {
    refreshing.value = false
  }
}

async function poll(): Promise<void> {
  await refresh()
  if (!disposed) timer = setTimeout(() => { void poll() }, activeCount.value ? 4000 : 15000)
}

async function upload({ file, onFinish, onError }: UploadCustomRequestOptions): Promise<void> {
  if (!file.file) { onError(); return }
  if (file.file.size > 20 * 1024 * 1024) {
    message.error('Максимальный размер файла — 20 МБ'); onError(); return
  }
  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', file.file)
    const { data } = await http.post<CheckJob>('/lavok-parser/checks', form, {
      timeout: 120000, headers: { 'Content-Type': 'multipart/form-data' },
    })
    jobs.value = [data, ...jobs.value.filter(j => j.id !== data.id)]
    message.success(`В очереди: ${data.total} компаний. Пропущено строк: ${data.rejected_rows}`)
    onFinish()
  } catch (err) {
    message.error(errorText(err, 'Не удалось отправить файл на проверку'))
    onError()
  } finally {
    uploading.value = false
  }
}

async function action(job: CheckJob, operation: 'cancel' | 'resume'): Promise<void> {
  busy.value[job.id] = true
  try {
    const { data } = await http.post<CheckJob>(`/lavok-parser/checks/${job.id}/${operation}`)
    jobs.value = jobs.value.map(j => j.id === data.id ? data : j)
    message.success(operation === 'cancel' ? 'Остановка запрошена. Сохранённые результаты останутся доступны' : 'Незавершённые проверки поставлены в очередь')
  } catch (err) {
    message.error(errorText(err, 'Не удалось изменить задание'))
  } finally { busy.value[job.id] = false }
}

async function download(job: CheckJob): Promise<void> {
  busy.value[job.id] = true
  try {
    const { data } = await http.get<Blob>(`/lavok-parser/checks/${job.id}/result.xlsx`, {
      responseType: 'blob', timeout: 600000,
    })
    const url = URL.createObjectURL(data)
    const link = document.createElement('a')
    link.href = url
    link.download = `Проверка компаний ${job.id.slice(0, 8)}.xlsx`
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (err) {
    message.error(errorText(err, 'Не удалось скачать Excel'))
  } finally { busy.value[job.id] = false }
}

onMounted(() => { void poll() })
onUnmounted(() => { disposed = true; if (timer) clearTimeout(timer) })
</script>

<template>
  <AppCard class="company-checks">
    <div class="company-checks__heading">
      <div>
        <h2>Проверка базы компаний</h2>
        <p>Загрузите Excel с ИНН. Проверим реестры, финансы, суды, долги и ЗСК; подготовим подробный Excel с фильтрами.</p>
      </div>
      <NUpload accept=".xlsx" :show-file-list="false" :disabled="uploading" :custom-request="upload">
        <NButton type="primary" :loading="uploading">Загрузить базу на проверку</NButton>
      </NUpload>
    </div>
    <NAlert v-if="connectionError" type="warning" :show-icon="true" style="margin-bottom: 12px">
      {{ connectionError }}. Сохранённые задания показаны ниже.
    </NAlert>
    <p class="company-checks__hint">До 20 МБ и 10 000 строк. Заголовок «ИНН» или «ИНН организации» может находиться ниже служебных строк. Повторы проверяются один раз. Страницу можно закрыть — обработка продолжится.</p>
    <NEmpty v-if="!jobs.length && !refreshing" description="Загрузите первую базу компаний" />
    <article v-for="job in jobs" :key="job.id" class="company-checks__job">
      <div class="company-checks__heading">
        <div>
          <strong>{{ job.filename }}</strong>
          <div class="company-checks__hint">{{ new Date(job.created_at).toLocaleString('ru-RU') }} · {{ job.total }} уникальных ИНН</div>
        </div>
        <NTag :type="job.status === 'completed' ? 'success' : job.failed_checks || job.status === 'failed' ? 'warning' : 'info'">
          {{ labels[job.status] || job.status }}
        </NTag>
      </div>
      <NProgress type="line" :percentage="job.progress" :status="job.status === 'completed' ? 'success' : 'default'" />
      <p>Компаний проверено: {{ job.completed }} / {{ job.total }}. Проверок: {{ job.checks_done }} / {{ job.checks_total }}.
        <template v-if="job.current_inn"> Сейчас: {{ job.source_label }}, ИНН {{ job.current_inn }}.</template>
      </p>
      <p class="company-checks__hint">Ошибок источников: {{ job.failed_checks }} · Строк пропущено: {{ job.rejected_rows }} · Повторов: {{ job.duplicates }} · Обновлено: {{ new Date(job.updated_at).toLocaleString('ru-RU') }}</p>
      <NAlert v-if="job.error" type="error" style="margin-bottom: 12px">{{ job.error }}</NAlert>
      <div class="company-checks__actions">
        <NButton v-if="job.result_ready" type="primary" :loading="busy[job.id]" @click="download(job)">Скачать подробный Excel</NButton>
        <NButton v-if="activeStates.has(job.status)" :disabled="busy[job.id]" @click="action(job, 'cancel')">Остановить с сохранением результатов</NButton>
        <NButton v-else-if="job.failed_checks || ['failed', 'cancelled'].includes(job.status)" :disabled="busy[job.id]" @click="action(job, 'resume')">Повторить незавершённые проверки</NButton>
      </div>
    </article>
  </AppCard>
</template>

<style scoped>
.company-checks h2 { margin: 0; font-size: 19px; }
.company-checks p { margin: 8px 0; }
.company-checks__heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.company-checks__hint { color: var(--text-color-secondary, #64748b); font-size: 13px; }
.company-checks__job { margin-top: 16px; padding: 16px; border: 1px solid var(--border-color, #dbe3ed); border-radius: 12px; }
.company-checks__job :deep(.n-progress) { margin-top: 12px; }
.company-checks__actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
</style>
