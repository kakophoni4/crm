<script setup lang="ts">
import { ref, onBeforeUnmount, onMounted } from 'vue'
import { NButton, NInput, NCheckbox, NSelect, NAlert } from 'naive-ui'
import { http } from '@/shared/api/http'
const emit = defineEmits<{ created: [] }>()
type PreparedRecord = {chat_id:string;system:string;messages:{role:string;content:string}[];answer:{reply:string;action:string;reason:string|null};selected:boolean}
const rows = ref<PreparedRecord[]>([]),
  index = ref(0),
  name = ref(''),
  notice = ref(''),
  error = ref(''),
  busy = ref(false),
  jobId = ref('')
let timer: ReturnType<typeof setInterval> | undefined
async function poll() {
  try {
    const { data } = await http.get('/ai/requests/' + jobId.value)
    if (data.status === 'succeeded') {
      rows.value = data.result.records.map((r: PreparedRecord) => ({ ...r, selected: false }))
      notice.value = [data.result.notice, ...data.result.warnings].join('\n')
      clearInterval(timer)
      busy.value = false
    } else if (data.status === 'failed') {
      error.value = data.error?.message || 'Не удалось разобрать архив'
      clearInterval(timer)
      busy.value = false
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    clearInterval(timer)
    busy.value = false
  }
}
async function upload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  busy.value = true
  error.value = ''
  try {
    if (file.size > 32 * 1024 * 1024) throw new Error('Максимум 32 МБ')
    const { data } = await http.post('/ai/prepare-export', file, {
      headers: { 'Content-Type': 'application/octet-stream' },
      timeout: 60000,
    })
    jobId.value = data.request_id
    clearInterval(timer)
    timer = setInterval(() => void poll(), 4000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    busy.value = false
  }
}
async function save() {
  busy.value = true
  error.value = ''
  try {
    const records = rows.value.filter((r) => r.selected).map(({ selected: _selected, ...r }) => r)
    if (!records.length) throw new Error('Выберите проверенные ответы')
    if (records.some((r) => !r.system.trim()))
      throw new Error('Укажите системный контекст для каждого выбранного ответа')
    await http.post('/ai/service/datasets', { name: name.value, records }, { timeout: 60000 })
    notice.value = 'Создан новый датасет. Просмотрите и отдельно одобрите его.'
    rows.value = []
    emit('created')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
onMounted(async () => {
  try {
    const { data } = await http.get('/ai/preparations')
    if (data.items[0]) {
      jobId.value = data.items[0].id
      await poll()
      if (['queued', 'running'].includes(data.items[0].status)) {
        busy.value = true
        timer = setInterval(() => void poll(), 4000)
      }
    }
  } catch {}
})
onBeforeUnmount(() => clearInterval(timer))
</script>
<template>
  <section class="prepare">
    <h3>Подготовить из переписок CRM</h3>
    <p>
      Архив обрабатывается в worker CRM. Выбирайте только подходящие ответы, проверяйте контекст и
      обезличивание.
    </p>
    <input type="file" accept=".jsonl,.gz" :disabled="busy" @change="upload" />
    <p v-if="busy">Обработка…</p>
    <NAlert v-if="error" type="error">{{ error }}</NAlert>
    <p v-if="notice" class="text">{{ notice }}</p>
    <div v-if="rows.length" class="editor">
      <NInput v-model:value="name" placeholder="Название датасета" /><NSelect
        v-model:value="index"
        :options="
          rows.map((r, i) => ({ label: `${i + 1}. ${r.answer.reply.slice(0, 65)}`, value: i }))
        "
      /><NCheckbox v-model:checked="rows[index].selected">Включить этот ответ в датасет</NCheckbox
      ><label
        >Системная инструкция и условия на момент ответа<NInput
          v-model:value="rows[index].system"
          type="textarea" /></label
      ><label v-for="(m, i) in rows[index].messages" :key="i"
        >{{ m.role === 'user' ? 'Клиент' : 'Сотрудник'
        }}<NInput v-model:value="m.content" type="textarea" /></label
      ><label
        >Эталонный ответ<NInput v-model:value="rows[index].answer.reply" type="textarea" /></label
      ><NSelect
        v-model:value="rows[index].answer.action"
        :options="[
          { label: 'Ответить', value: 'reply' },
          { label: 'Передать менеджеру', value: 'handoff' },
          { label: 'Без ответа', value: 'no_reply' },
        ]"
      /><NInput v-model:value="rows[index].answer.reason" placeholder="Причина" /><NButton
        :disabled="busy || !name.trim()"
        @click="save"
        >Создать датасет из выбранных ответов</NButton
      >
    </div>
  </section>
</template>
<style scoped>
.prepare,
.editor {
  display: grid;
  gap: 12px;
  min-width: 0;
}
.prepare {
  border-top: 1px solid var(--app-border);
  padding-top: 20px;
}
.text {
  white-space: pre-wrap;
}
label {
  display: grid;
  gap: 6px;
}
input {
  max-width: 100%;
}
</style>
