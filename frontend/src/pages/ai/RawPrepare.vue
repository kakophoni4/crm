<script setup lang="ts">
import { computed, ref, onBeforeUnmount, onMounted } from 'vue'
import { NButton, NInput, NCheckbox, NSelect, NAlert } from 'naive-ui'
import { http } from '@/shared/api/http'
const emit = defineEmits<{ created: [] }>()
const sourceChats = ref<{ id: number; name: string; last_message_at: string }[]>([])
const chosenChats = ref<number[]>([])
const search = ref(''),
  sourceOffset = ref(0),
  hasMore = ref(false),
  sourceBusy = ref(false)
const commonInstruction = ref('')
const chosenCount = computed(() => rows.value.filter((r) => r.selected).length)
const chosenDialogCount = computed(
  () => new Set(rows.value.filter((r) => r.selected).map((r) => r.chat_id)).size,
)
async function loadChats(reset = false) {
  sourceBusy.value = true
  error.value = ''
  if (reset) sourceOffset.value = 0
  try {
    const { data } = await http.get('/ai/source-chats', {
      params: { query: search.value, offset: sourceOffset.value },
    })
    sourceChats.value = data.items
    hasMore.value = data.has_more
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    sourceBusy.value = false
  }
}
async function prepareChats() {
  busy.value = true
  error.value = ''
  try {
    const { data } = await http.post(
      '/ai/prepare-chats',
      { chat_ids: chosenChats.value },
      { timeout: 60000 },
    )
    rows.value = []
    index.value = 0
    jobId.value = data.request_id
    clearInterval(timer)
    timer = setInterval(() => void poll(), 4000)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
    busy.value = false
  }
}
function reviewCurrent(include: boolean) {
  rows.value[index.value].selected = include
  if (index.value < rows.value.length - 1) index.value++
}

type PreparedRecord = {
  chat_id: string
  system: string
  messages: { role: string; content: string }[]
  answer: { reply: string; action: string; reason: string | null }
  selected: boolean
}
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
      index.value = 0
      rows.value = data.result.records.map((r: PreparedRecord) => ({ ...r, selected: false }))
      notice.value = [
        data.result.records.length
          ? ''
          : 'Подходящих ответов сотрудников не найдено. Выберите другие диалоги с текстовыми вопросами клиентов и ответами людей.',
        data.result.notice,
        ...data.result.warnings,
      ]
        .filter(Boolean)
        .join('\n')
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
    notice.value =
      'Учебный набор создан. Ниже откройте его, проверьте и разрешите использовать для обучения.'
    rows.value = []
    emit('created')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
onMounted(async () => {
  void loadChats()
  try {
    const { data } = await http.get('/ai/service/prompts?limit=1')
    if (data.active_prompt_id) {
      const active = await http.get('/ai/service/prompts/' + data.active_prompt_id)
      commonInstruction.value = active.data.content
    }
  } catch {
    /* The CRM source chooser remains usable while the AI service is unavailable. */
  }
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
    <h3>1. Выберите переписки из CRM</h3>
    <p>
      Отметьте диалоги с хорошими ответами сотрудников. Ничего скачивать не нужно. За раз — до 20
      диалогов, по 500 последних сообщений; просмотр покажет до 10 ответов на диалог (до 200 всего).
      Вложения не читаются.
    </p>
    <div class="actions">
      <NInput
        v-model:value="search"
        placeholder="Найти клиента по имени или номеру чата"
        @keyup.enter="loadChats(true)"
      /><NButton :disabled="sourceBusy || busy" @click="loadChats(true)">Найти</NButton>
    </div>
    <div class="chat-list" aria-label="Переписки для обучения">
      <label v-for="chat in sourceChats" :key="chat.id" class="chat-choice">
        <NCheckbox
          :checked="chosenChats.includes(chat.id)"
          :disabled="busy || (!chosenChats.includes(chat.id) && chosenChats.length >= 20)"
          @update:checked="
            (checked) => {
              chosenChats = checked
                ? [...chosenChats, chat.id]
                : chosenChats.filter((id) => id !== chat.id)
            }
          "
          >{{ chat.name }} · чат №{{ chat.id }}</NCheckbox
        >
        <small>{{ new Date(chat.last_message_at).toLocaleString('ru-RU') }}</small>
      </label>
      <p v-if="!sourceChats.length && !sourceBusy">
        Диалоги не найдены. Попробуйте другое имя или очистите поиск.
      </p>
    </div>
    <div class="actions">
      <NButton
        :disabled="sourceBusy || busy || sourceOffset === 0"
        @click="
          () => {
            sourceOffset -= 30
            loadChats()
          }
        "
        >Назад</NButton
      ><NButton
        :disabled="sourceBusy || busy || !hasMore"
        @click="
          () => {
            sourceOffset += 30
            loadChats()
          }
        "
        >Ещё диалоги</NButton
      ><span>Выбрано {{ chosenChats.length }} из 20</span>
    </div>
    <NButton type="primary" :disabled="busy || !chosenChats.length" @click="prepareChats"
      >Показать ответы из выбранных диалогов</NButton
    >
    <details>
      <summary>Другой способ: загрузить файл переписок</summary>
      <p>Если переписки находятся вне CRM: файл JSONL или GZ до 32 МБ.</p>
      <input type="file" accept=".jsonl,.gz" :disabled="busy" @change="upload" />
    </details>
    <p v-if="busy">Готовим материал… Можно дождаться здесь или вернуться позже.</p>
    <NAlert v-if="error" type="error">{{ error }}</NAlert>
    <p v-if="notice" class="text">{{ notice }}</p>
    <div v-if="rows.length" class="editor">
      <h3>2. Проверьте и исправьте ответы</h3>
      <p>
        Правки сохраняются при переходе между шагами. До обновления страницы сохраните их в учебный
        набор.
      </p>
      <p>
        Читайте переписку и исправляйте ответ так, как должен отвечать помощник. «Взять» включает
        его в обучение, «Пропустить» исключает.
      </p>
      <label
        >Название учебного набора<NInput
          v-model:value="name"
          placeholder="Например: Ответы по услугам · сентябрь"
      /></label>
      <details>
        <summary>Одна инструкция для всех этих примеров</summary>
        <p>
          Укажите правила, действовавшие в этих диалогах. Кнопка заполнит только пустые инструкции.
        </p>
        <NInput
          v-model:value="commonInstruction"
          type="textarea"
          placeholder="Роль помощника, правила и условия ответа"
        /><NButton
          :disabled="!commonInstruction.trim()"
          @click="
            () => {
              rows.forEach((r) => {
                if (!r.system.trim()) r.system = commonInstruction
              })
            }
          "
          >Заполнить пустые инструкции</NButton
        >
      </details>
      <p>
        Ответ {{ index + 1 }} из {{ rows.length }} · Взято {{ chosenCount }} ответов из
        {{ chosenDialogCount }} диалогов
      </p>
      <NSelect
        v-model:value="index"
        :options="
          rows.map((r, i) => ({ label: `${i + 1}. ${r.answer.reply.slice(0, 65)}`, value: i }))
        "
      /><NCheckbox v-model:checked="rows[index].selected"
        >Этот ответ проверен и подходит для обучения</NCheckbox
      ><label
        >Правила и условия, по которым дан этот ответ<NInput
          v-model:value="rows[index].system"
          type="textarea" /></label
      ><label v-for="(m, i) in rows[index].messages" :key="i"
        >{{ m.role === 'user' ? 'Клиент' : 'Сотрудник'
        }}<NInput v-model:value="m.content" type="textarea" /></label
      ><label
        >Как помощник должен ответить<NInput
          v-model:value="rows[index].answer.reply"
          type="textarea" /></label
      ><NSelect
        v-model:value="rows[index].answer.action"
        :options="[
          { label: 'Ответить', value: 'reply' },
          { label: 'Передать менеджеру', value: 'handoff' },
          { label: 'Без ответа', value: 'no_reply' },
        ]"
      /><NInput
        v-model:value="rows[index].answer.reason"
        placeholder="Почему передать менеджеру или не отвечать (если нужно)"
      />
      <div class="actions">
        <NButton
          :disabled="index === 0"
          @click="
            () => {
              index--
            }
          "
          >Предыдущий ответ</NButton
        ><NButton @click="reviewCurrent(false)">Пропустить</NButton
        ><NButton type="primary" :disabled="!rows[index].system.trim()" @click="reviewCurrent(true)"
          >Взять и перейти дальше</NButton
        >
      </div>
      <h3>3. Сохраните материал</h3>
      <p>
        Для обучения нужны минимум 20 уникальных примеров из 5 диалогов. Выбрано:
        {{ chosenCount }} ответов из {{ chosenDialogCount }} диалогов. Сохранить промежуточный набор
        можно и раньше.
      </p>
      <NButton :disabled="busy || !name.trim() || !chosenCount" @click="save"
        >Сохранить выбранные ответы в учебный набор</NButton
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
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.actions > .n-input {
  flex: 1 1 240px;
}
.chat-list {
  display: grid;
  gap: 10px;
  max-height: 360px;
  overflow-y: auto;
}
.chat-choice {
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 12px;
  overflow-wrap: anywhere;
}
small {
  color: var(--app-text-muted);
}
summary {
  cursor: pointer;
  font-weight: 600;
}
</style>
