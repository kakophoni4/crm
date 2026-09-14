<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NModal, NAlert, useMessage } from 'naive-ui'
import { useAuthStore } from '@/shared/store/auth'
import { http } from '@/shared/api/http'
const auth = useAuthStore(),
  message = useMessage()
const emit = defineEmits<{ imported: [] }>()
const input = ref<HTMLInputElement | null>(null),
  busy = ref(false),
  show = ref(false),
  file = ref<File | null>(null)
type Preview = {
  deals: number
  operations: number
  skipped: number
  account_changes: Record<string, string>
  warnings: string[]
}
const preview = ref<Preview | null>(null)
const errorText = (e: any) =>
  e?.response?.data?.error?.message || e?.message || 'Не удалось импортировать файл'
async function request(apply = false) {
  const data = new FormData()
  data.append('file', file.value!)
  return (
    await http.post<Preview>('/cashroom/import-excel', data, {
      params: { apply },
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  ).data
}
async function selectFile(event: Event) {
  const el = event.target as HTMLInputElement
  file.value = el.files?.[0] ?? null
  el.value = ''
  if (!file.value) return
  if (file.value.size > 5000000) {
    message.error('Файл не должен превышать 5 МБ')
    return
  }
  busy.value = true
  preview.value = null
  try {
    preview.value = await request()
    show.value = true
  } catch (e) {
    message.error(errorText(e))
  } finally {
    busy.value = false
  }
}
async function apply() {
  if (busy.value) return
  busy.value = true
  try {
    const result = await request(true)
    show.value = false
    message.success(
      `Добавлено сделок: ${result.deals}, кассовых операций: ${result.operations}. Пропущено повторов: ${result.skipped}`,
    )
    emit('imported')
  } catch (e) {
    message.error(errorText(e))
  } finally {
    busy.value = false
  }
}
</script>
<template>
  <template v-if="auth.isAdmin">
    <input ref="input" type="file" accept=".xlsx" hidden @change="selectFile" />
    <NButton :loading="busy" @click="input?.click()">Импорт Excel</NButton>
    <NModal
      v-model:show="show"
      preset="card"
      title="Импорт реестра"
      class="cash-import-modal"
      :mask-closable="!busy"
      :closable="!busy"
      :close-on-esc="!busy"
    >
      <template v-if="preview">
        <p>
          Новых сделок: <b>{{ preview.deals }}</b
          >. Операций второго листа: <b>{{ preview.operations }}</b
          >. Уже загружено: <b>{{ preview.skipped }}</b
          >.
        </p>
        <NAlert type="info"
          >Получения и выдачи по сделкам попадут в кассу 1. Операции второго листа — в указанные в
          нём кассы. Существующие записи не заменяются.</NAlert
        >
        <h3>Изменение остатков</h3>
        <p v-for="(amount, account) in preview.account_changes" :key="account">
          Касса {{ account }}:
          {{ Number(amount).toLocaleString('ru-RU', { style: 'currency', currency: 'RUB' }) }}
        </p>
        <details v-if="preview.warnings.length">
          <summary>Примечания к импорту · {{ preview.warnings.length }}</summary>
          <p v-for="warning in preview.warnings" :key="warning">{{ warning }}</p>
        </details>
        <div class="import-actions">
          <NButton :disabled="busy" @click="show = false">Закрыть</NButton
          ><NButton
            type="primary"
            :loading="busy"
            :disabled="!preview.deals && !preview.operations"
            @click="apply"
            >Загрузить в CRM</NButton
          >
        </div>
      </template>
    </NModal>
  </template>
</template>
<style scoped>
.import-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
}
details {
  margin-top: 16px;
}
summary {
  cursor: pointer;
}
</style>
<style>
.cash-import-modal.n-card {
  width: min(600px, calc(100vw - 24px));
  max-height: calc(100dvh - 32px);
  overflow-y: auto;
  overflow-wrap: anywhere;
}
</style>
