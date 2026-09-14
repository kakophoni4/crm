<script setup lang="ts">
import { ref, reactive, onMounted, onBeforeUnmount, watch } from 'vue'
import {
  NButton,
  NInput,
  NInputNumber,
  NSelect,
  NCheckbox,
  NAlert,
  NTag,
  useMessage,
} from 'naive-ui'
import RawPrepare from './RawPrepare.vue'
import { http } from '@/shared/api/http'

// External resources have different schemas; writable form fields are selected explicitly.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Item = Record<string, any>
const toast = useMessage()
let promptInitialized = false
const testPrompts = ref<Item[]>([])
const activeTestPrompt = ref<number | null>(null)
const tabs = [
  'Настройки',
  'Инструкция',
  'Каталог',
  'Тестовый чат',
  'Примеры',
  'Датасеты',
  'Обучение',
  'Версии моделей',
  'Журнал',
]
const page = ref(0),
  datasetOffset = ref(0),
  datasets = ref<Item[]>([]),
  logJob = ref(''),
  logCursor = ref(0),
  logs = ref<Item[]>([])
const tab = ref(1),
  busy = ref(false),
  error = ref('')
const connection = reactive<Item>({}),
  status = ref<Item>({}),
  resources = ref<Item>({})
const items = ref<Item[]>([]),
  requests = ref<Item[]>([]),
  models = ref<Item[]>([])
const catalogRevision = ref('')
const title = ref(''),
  content = ref(''),
  catalog = ref(''),
  catalogVersion = ref(0)
const liveRequests = ref<Item[]>([]),
  liveId = ref<string | null>(null)
const question = ref(''),
  promptId = ref<number | null>(null),
  candidateId = ref<string | null>(null)
const selected = ref<Item | null>(null),
  answer = ref(''),
  note = ref(''),
  action = ref('reply'),
  reason = ref('')
const datasetName = ref(''),
  datasetId = ref(''),
  baseModel = ref<string | null>(null)
const epochs = ref(1),
  maxLength = ref(1024),
  rate = ref(0.0001),
  seed = ref(42)
const reviewed = ref(false),
  anonymized = ref(false),
  servicesOnly = ref(false),
  qualityReviewed = ref(false)
const history = ref<{ role: string; content: string }[]>([])
let timer: ReturnType<typeof setInterval> | undefined
const loading = ref(false)
const get = async (path: string) => (await http.get('/ai/' + path, { timeout: 45000 })).data
const api = async (path: string, data: unknown = {}, method = 'post') =>
  (await http.request({ url: '/ai/service/' + path, method, data, timeout: 45000 })).data
const labels: Record<string, string> = {
  queued: 'В очереди',
  running: 'Выполняется',
  succeeded: 'Завершено',
  failed: 'Ошибка',
  cancelled: 'Отменено',
  pending: 'Ожидается',
  uncertain: 'Результат требует проверки',
}
async function run(fn: () => Promise<void>) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await fn()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
async function refresh() {
  if (loading.value) return
  loading.value = true
  try {
    if (tab.value === 0) {
      status.value = await get('status')
      Object.assign(connection, await get('service/connection'))
    }
    if (tab.value === 1) {
      const data = await get('service/prompts?limit=50&offset=' + page.value * 50)
      items.value = data.items
      selected.value = { active_prompt_id: data.active_prompt_id }
      if (!promptInitialized && !content.value && !title.value) {
        if (data.active_prompt_id) {
          const active = await get('service/prompts/' + data.active_prompt_id)
          content.value = active.content
          title.value = (active.title + ' — правки').slice(0, 120)
        }
        promptInitialized = true
      }
    }
    if (tab.value === 2) {
      const data = await get('service/catalog')
      catalog.value = data.content
      catalogVersion.value = data.version
      catalogRevision.value = data._crm_revision
    }
    if (tab.value === 3) {
      requests.value = (await get('requests')).items
      const prompts = await get('service/prompts?limit=200')
      testPrompts.value = prompts.items
      activeTestPrompt.value = prompts.active_prompt_id || null
    }
    if (tab.value === 4) {
      items.value = (await get('service/examples?limit=50&offset=' + page.value * 50)).items
      liveRequests.value = (await get('requests?live=true')).items
    }
    if (tab.value === 5)
      items.value = (await get('service/datasets?limit=50&offset=' + page.value * 50)).items
    if (tab.value === 6) {
      resources.value = await get('service/training/status')
      datasets.value = (await get('service/datasets?limit=200')).items
      items.value = (await get('service/training/jobs?limit=50&offset=' + page.value * 50)).items
      if (logJob.value) {
        const batch = await get(
          `service/training/jobs/${logJob.value}/logs?after_id=${logCursor.value}`,
        )
        logs.value = [...logs.value, ...batch.items].slice(-500)
        logCursor.value = batch.next_after_id
      }
    }
    if (tab.value === 7) {
      items.value = (await get('service/model-versions')).items
      Object.assign(connection, await get('service/connection'))
    }
    if (tab.value === 8) items.value = (await get('journal')).items
  } finally {
    loading.value = false
  }
}
async function mutate(path: string, body: unknown = {}, method = 'post') {
  await run(async () => {
    await api(path, body, method)
    toast.success('Сохранено')
    await refresh()
  })
}
async function test() {
  if (!question.value.trim()) return
  await run(async () => {
    const prompts = await get('service/prompts?limit=200')
    testPrompts.value = prompts.items
    activeTestPrompt.value = prompts.active_prompt_id || null
    const resolvedPrompt = promptId.value || activeTestPrompt.value
    if (!resolvedPrompt)
      throw new Error(
        'Выберите сохранённую инструкцию ниже или создайте её во вкладке «Инструкция». Активировать её для теста необязательно.',
      )
    const messages = [...history.value, { role: 'user', content: question.value }]
    await api(candidateId.value ? `model-versions/${candidateId.value}/test` : 'test/replies', {
      messages,
      mode: 'assistant',
      context: { manager_notified: false },
      prompt_id: resolvedPrompt,
    })
    question.value = ''
    await refresh()
  })
}
async function exportExamples() {
  await run(async () => {
    let after = '0'
    const chunks: string[] = []
    for (let i = 0; i < 100; i++) {
      const data = await get('service/examples/export?limit=500&after_id=' + after)
      if (!data.content) break
      chunks.push(data.content)
      if (!data.next_after_id) break
      after = data.next_after_id
    }
    const url = URL.createObjectURL(new Blob(chunks, { type: 'application/x-ndjson' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'approved-examples.jsonl'
    a.click()
    URL.revokeObjectURL(url)
  })
}
async function upload(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  await run(async () => {
    if (!datasetName.value.trim()) throw new Error('Укажите название датасета')
    if (file.size > 32 * 1024 * 1024) throw new Error('Максимальный размер — 32 МБ')
    await http.post('/ai/service/datasets/import', file, {
      params: { name: datasetName.value },
      headers: { 'Content-Type': 'application/octet-stream' },
      timeout: 60000,
    })
    toast.success('Датасет загружен. Для обучения требуется отдельное одобрение.')
    await refresh()
  })
}
function selectLiveRequest(id: string) {
  const item = liveRequests.value.find((r) => r.id === id)
  if (!item?.result) return
  selected.value = { source_request_id: id }
  answer.value = item.result.reply
  action.value = item.result.action
  reason.value = item.result.reason || ''
  note.value = ''
}
function editExample(item: Item) {
  selected.value = item
  answer.value = item.answer?.reply || ''
  action.value = item.answer?.action || 'reply'
  reason.value = item.answer?.reason || ''
  note.value = item.note || ''
}
watch(
  tab,
  () => {
    page.value = 0
    items.value = []
    selected.value = null
    logJob.value = ''
    logs.value = []
    void run(refresh)
  },
  { flush: 'sync' },
)
onMounted(() => {
  void run(refresh)
  timer = setInterval(() => {
    if ([3, 6].includes(tab.value) && !busy.value)
      void refresh().catch((e) => {
        error.value = e.message
      })
  }, 4000)
})
onBeforeUnmount(() => {
  clearInterval(timer)
})
</script>

<template>
  <main class="ai-page">
    <header>
      <div>
        <p class="eyebrow">РАБОЧЕЕ ПРОСТРАНСТВО АДМИНИСТРАТОРА</p>
        <h1>Управление ИИ</h1>
        <p>Инструкции, проверенные ответы и обучение — в одном месте.</p>
      </div>
      <NButton
        :loading="busy"
        @click="
          () => {
            run(refresh)
          }
        "
        >Обновить</NButton
      >
    </header>
    <nav aria-label="Разделы управления ИИ">
      <button
        :disabled="busy || loading"
        v-for="(label, i) in tabs"
        :key="label"
        :class="{ active: tab === i }"
        @click="
          () => {
            tab = i
          }
        "
      >
        {{ label }}
      </button>
    </nav>
    <div v-if="[1, 4, 5, 6].includes(tab) && (page > 0 || items.length >= 50)" class="actions">
      <NButton
        :disabled="busy || page === 0"
        @click="
          () => {
            page--
            run(refresh)
          }
        "
        >Предыдущая страница</NButton
      ><span>Страница {{ page + 1 }}</span
      ><NButton
        :disabled="busy || items.length < 50"
        @click="
          () => {
            page++
            run(refresh)
          }
        "
        >Следующая страница</NButton
      >
    </div>
    <NAlert v-if="error" type="error" closable @close="error = ''">{{ error }}</NAlert>
    <section v-if="tab === 0" class="panel">
      <h2>Настройки ИИ</h2>
      <div class="actions">
        <NTag
          :type="status.reply_key_configured && status.admin_key_configured ? 'success' : 'warning'"
        >
          {{
            status.reply_key_configured && status.admin_key_configured
              ? 'Ключи подключения настроены'
              : 'Нужно настроить ключи на сервере'
          }}
        </NTag>
      </div>
      <p class="muted">Рабочая модель: {{ connection.model || 'Загрузка…' }}</p>
      <NAlert :type="status.auto_replies_enabled ? 'info' : 'warning'"
        >Автоответы клиентам
        {{ status.auto_replies_enabled ? 'разрешены сервером' : 'выключены сервером' }}. Проверка
        подключения не подтверждает генерацию и обучение.</NAlert
      >
      <details v-if="Object.keys(connection).length" class="advanced">
        <summary>Модель и дополнительные настройки</summary>
        <p class="muted">Меняйте только при необходимости. Подключение к Ollama уже настроено.</p>
        <div class="form-grid">
          <label
            >Модель<NInput v-model:value="connection.model" /><NSelect
              v-if="models.length"
              v-model:value="connection.model"
              :options="
                models.map((m) => ({ label: m.name || m.model, value: m.name || m.model }))
              "
          /></label>
          <label
            >Ожидание ответа, секунд<NInputNumber
              v-model:value="connection.timeout_seconds"
              :min="5"
              :max="600"
          /></label>
          <label
            >Объём контекста, токенов<NInputNumber
              v-model:value="connection.num_ctx"
              :min="1024"
              :max="32768"
          /></label>
          <label
            >Максимум ответа, токенов<NInputNumber
              v-model:value="connection.num_predict"
              :min="32"
              :max="2048"
          /></label>
          <label
            >Разнообразие ответов (температура)<NInputNumber
              v-model:value="connection.temperature"
              :min="0"
              :max="1.5"
              :step="0.1"
          /></label>
        </div>
        <div class="actions">
          <NButton
            :disabled="busy || !Object.keys(connection).length"
            type="primary"
            @click="
              () => {
                mutate(
                  'connection',
                  Object.fromEntries(
                    [
                      'base_url',
                      'model',
                      'timeout_seconds',
                      'num_ctx',
                      'num_predict',
                      'temperature',
                      '_crm_revision',
                    ].map((k) => [k, connection[k]]),
                  ),
                  'put',
                )
              }
            "
            >Сохранить</NButton
          ><NButton
            :disabled="busy"
            @click="
              () => {
                run(async () => {
                  const r = await get('service/models')
                  models = r.models || r.items || []
                })
              }
            "
            >Обновить список моделей</NButton
          >
        </div>
      </details>
      <div class="actions">
        <NButton
          :disabled="busy"
          @click="
            () => {
              run(async () => {
                selected = await api('connection/check')
              })
            }
          "
          >Проверить подключение</NButton
        >
      </div>
      <NAlert
        v-if="selected"
        :type="selected.reachable && selected.model_available ? 'success' : 'warning'"
      >
        {{
          selected.reachable
            ? selected.model_available
              ? 'Подключение работает, модель доступна.'
              : 'Сервер доступен, выбранная модель не найдена.'
            : 'Не удалось подтвердить подключение.'
        }}
        Для проверки ответа откройте тестовый чат.
      </NAlert>
    </section>
    <section v-if="tab === 1" class="panel prompt-panel">
      <div>
        <p class="eyebrow">ПОВЕДЕНИЕ ИИ</p>
        <h2>Как ИИ должен общаться</h2>
        <p class="muted">
          Опишите стиль общения, какие вопросы задавать и когда звать менеджера. Цены и услуги
          удобнее хранить в каталоге.
        </p>
      </div>
      <div class="prompt-steps">
        <span>1. Напишите инструкцию</span><span>2. Сохраните и проверьте</span
        ><span>3. Включите версию</span>
      </div>
      <label
        >Название версии
        <NInput
          v-model:value="title"
          placeholder="Например: Короткие ответы · сентябрь"
          :maxlength="120"
      /></label>
      <label
        >Инструкция
        <NInput
          v-model:value="content"
          type="textarea"
          :autosize="{ minRows: 16, maxRows: 32 }"
          :maxlength="16000"
          show-count
          placeholder="Роль и стиль общения
Какую задачу ты помогаешь решить клиенту? Как обращаешься к нему?

Порядок ответа
Что нужно уточнить перед ответом?

Передача менеджеру
В каких случаях нужно пригласить человека?"
        />
      </label>
      <div class="prompt-footer">
        <p class="muted">
          Сохранение создаёт новую версию. Чтобы использовать её в ответах, нажмите «Включить» после
          проверки.
        </p>
        <NButton
          :disabled="busy || !title.trim() || !content.trim()"
          type="primary"
          @click="
            () => {
              mutate('prompts', { title, content })
            }
          "
          >Сохранить новую версию</NButton
        >
      </div>
      <div class="version-heading">
        <h3>Сохранённые версии</h3>
        <NTag v-if="selected?.active_prompt_id"
          >Рабочая версия №{{ selected.active_prompt_id }}</NTag
        >
      </div>
      <p v-if="!items.length && !busy" class="muted">Пока нет версий. Начните с инструкции выше.</p>
      <article
        v-for="item in items"
        :key="item.id"
        class="prompt-version"
        :class="{ 'is-active': selected?.active_prompt_id === item.id }"
      >
        <div class="version-heading">
          <h3>{{ item.title }}</h3>
          <NTag v-if="selected?.active_prompt_id === item.id" type="success"
            >Используется сейчас</NTag
          >
        </div>
        <details>
          <summary>Посмотреть текст инструкции</summary>
          <p class="text">{{ item.content }}</p>
        </details>
        <div class="actions">
          <NButton
            :disabled="busy"
            @click="
              () => {
                run(async () => {
                  content = (await get('service/prompts/' + item.id)).content
                  title = (item.title + ' — правки').slice(0, 120)
                })
              }
            "
            >Редактировать копию</NButton
          >
          <NButton
            :disabled="busy"
            @click="
              () => {
                promptId = item.id
                candidateId = null
                tab = 3
              }
            "
            >Проверить в чате</NButton
          >
          <NButton
            :disabled="busy || selected?.active_prompt_id === item.id"
            type="primary"
            secondary
            @click="
              () => {
                mutate(`prompts/${item.id}/activate`)
              }
            "
            >Включить</NButton
          >
        </div>
      </article>
    </section>
    <section v-if="tab === 2" class="panel">
      <h2>Каталог · версия {{ catalogVersion }}</h2>
      <p>Услуги, условия, цены, сроки и ограничения.</p>
      <NInput
        v-model:value="catalog"
        type="textarea"
        :autosize="{ minRows: 16 }"
        :maxlength="24000"
      /><NButton
        type="primary"
        :disabled="busy"
        @click="
          () => {
            mutate('catalog', { content: catalog, _crm_revision: catalogRevision }, 'put')
          }
        "
        >Сохранить каталог</NButton
      >
    </section>
    <section v-if="tab === 3" class="panel">
      <h2>Тестовый чат</h2>
      <label
        >Инструкция для теста
        <NSelect
          v-model:value="promptId"
          clearable
          :disabled="busy"
          :placeholder="
            activeTestPrompt
              ? 'Рабочая инструкция №' + activeTestPrompt
              : 'Выберите сохранённую инструкцию'
          "
          :options="
            testPrompts.map((p) => ({
              label: p.title + (p.id === activeTestPrompt ? ' · рабочая' : ''),
              value: p.id,
            }))
          "
        />
      </label>
      <NAlert v-if="!promptId && !activeTestPrompt && !busy" type="warning">
        Для теста нужна инструкция. Выберите сохранённую версию в списке; включать её для клиентов
        не требуется.
        <NButton
          text
          @click="
            () => {
              tab = 1
            }
          "
          >Открыть инструкции</NButton
        >
      </NAlert>
      <p>
        Клиенты не получают эти сообщения. Промпт: {{ promptId || 'активный' }}. Модель:
        {{ candidateId || 'рабочая' }}.
      </p>
      <div class="actions">
        <NButton
          @click="
            () => {
              history = []
              candidateId = null
            }
          "
          >Начать новый диалог</NButton
        >
      </div>
      <p>Очистка диалога не удаляет историю на ИИ-сервисе.</p>
      <NInput
        v-model:value="question"
        type="textarea"
        placeholder="Проверьте реальный вопрос клиента"
      /><NButton
        type="primary"
        :disabled="busy || !question.trim() || (!promptId && !activeTestPrompt)"
        @click="
          () => {
            test()
          }
        "
        >Отправить тест</NButton
      >
      <article v-for="item in requests" :key="item.id">
        <NTag>{{ labels[item.status] || item.status }}</NTag>
        <p class="text">{{ item.body.messages?.at(-1)?.content }}</p>
        <p v-if="item.result" class="text answer">
          {{ item.result.reply || 'Без сообщения клиенту' }}
        </p>
        <p v-if="item.error">{{ item.error.message }}</p>
        <details v-if="item.result">
          <summary>Параметры ответа</summary>
          <p>{{ item.id }}</p>
          <p
            v-for="key in ['action', 'reason', 'model', 'prompt_version', 'catalog_version']"
            :key="key"
          >
            {{ key }}: {{ item.result?.[key] }}
          </p>
        </details>
        <div v-if="item.result" class="actions">
          <NButton
            @click="
              () => {
                history = [
                  ...item.body.messages,
                  ...(item.result.reply ? [{ role: 'assistant', content: item.result.reply }] : []),
                ]
                promptId = item.body.prompt_id || null
              }
            "
            >Продолжить этот диалог</NButton
          ><NButton
            @click="
              () => {
                tab = 4
                selected = { source_request_id: item.id }
                answer = item.result.reply
                action = item.result.action
                reason = item.result.reason || ''
              }
            "
            >Исправить / сохранить пример</NButton
          >
        </div>
      </article>
    </section>
    <section v-if="tab === 4" class="panel">
      <h2>Проверенные примеры</h2>
      <label
        >Сохранить или исправить ответ из рабочего чата<NSelect
          v-model:value="liveId"
          :options="
            liveRequests
              .filter((r) => r.status === 'delivered')
              .map((r) => ({ label: r.result.reply.slice(0, 100), value: r.id }))
          "
          @update:value="
            (v) => {
              if (typeof v === 'string') selectLiveRequest(v)
            }
          "
      /></label>
      <NButton
        :disabled="busy"
        @click="
          () => {
            exportExamples()
          }
        "
        >Экспорт одобренных</NButton
      >
      <div v-if="selected" class="editor">
        <NInput v-model:value="answer" type="textarea" placeholder="Эталонный ответ" /><NSelect
          v-model:value="action"
          :options="[
            { label: 'Ответить', value: 'reply' },
            { label: 'Передать менеджеру', value: 'handoff' },
            { label: 'Не отвечать', value: 'no_reply' },
          ]"
        /><NInput
          v-model:value="reason"
          placeholder="Причина передачи / отсутствия ответа"
        /><NInput v-model:value="note" placeholder="Комментарий для проверки" /><NButton
          :disabled="busy"
          @click="
            () => {
              mutate(
                selected!.id ? `examples/${selected!.id}` : 'examples',
                {
                  ...(selected!.id ? {} : { source_request_id: selected!.source_request_id }),
                  answer: { reply: answer, action, reason: reason || null },
                  note,
                },
                selected!.id ? 'patch' : 'post',
              )
            }
          "
          >Сохранить без одобрения</NButton
        >
      </div>
      <article v-for="item in items" :key="item.id">
        <NTag>{{ item.approved ? 'Одобрен' : 'Нужна проверка' }}</NTag>
        <details>
          <summary>Контекст</summary>
          <p v-for="(m, i) in item.messages" :key="i" class="text">{{ m.role }}: {{ m.content }}</p>
        </details>
        <p class="text">{{ item.answer?.reply }}</p>
        <p>{{ item.note }}</p>
        <div class="actions">
          <NButton
            @click="
              () => {
                editExample(item)
              }
            "
            >Исправить</NButton
          ><NButton
            :disabled="busy || item.approved"
            @click="
              () => {
                mutate(`examples/${item.id}/approve`)
              }
            "
            >Одобрить</NButton
          ><NButton
            :disabled="busy"
            @click="
              () => {
                mutate(`examples/${item.id}`, {}, 'delete')
              }
            "
            >Удалить</NButton
          >
        </div>
      </article>
    </section>
    <section v-if="tab === 5" class="panel">
      <h2>Датасеты</h2>
      <RawPrepare @created="run(refresh)" /><NInput
        v-model:value="datasetName"
        placeholder="Название нового датасета"
      /><label class="upload"
        >Загрузить подготовленный JSONL / GZ<input
          type="file"
          accept=".jsonl,.gz"
          :disabled="busy"
          @change="upload" /></label
      ><NButton
        :disabled="busy || !datasetName.trim()"
        @click="
          () => {
            mutate('datasets/from-approved?name=' + encodeURIComponent(datasetName))
          }
        "
        >Собрать из одобренных примеров</NButton
      >
      <p>
        Загрузка не означает одобрение. Для обучения нужно минимум 20 уникальных примеров из 5
        диалогов.
      </p>
      <article v-for="item in items" :key="item.id">
        <h3>{{ item.name }}</h3>
        <p>{{ item.approved ? 'одобрен' : 'ожидает проверки' }}</p>
        <NButton
          @click="
            () => {
              run(async () => {
                datasetOffset = 0
                selected = await get('service/datasets/' + item.id)
                reviewed = false
                anonymized = false
                servicesOnly = false
              })
            }
          "
          >Просмотреть и проверить</NButton
        >
      </article>
      <div v-if="selected">
        <h3>{{ selected.name }} · {{ selected.count }} примеров</h3>
        <div class="actions">
          <NButton
            :disabled="busy || datasetOffset === 0"
            @click="
              () => {
                run(async () => {
                  datasetOffset -= 50
                  selected = await get(`service/datasets/${selected!.id}?offset=${datasetOffset}`)
                })
              }
            "
            >Предыдущие записи</NButton
          ><NButton
            :disabled="busy || datasetOffset + 50 >= selected.count"
            @click="
              () => {
                run(async () => {
                  datasetOffset += 50
                  selected = await get(`service/datasets/${selected!.id}?offset=${datasetOffset}`)
                })
              }
            "
            >Следующие записи</NButton
          >
        </div>
        <article v-for="(record, i) in selected.records || selected.items || []" :key="i">
          <p class="text">{{ record.system }}</p>
          <p v-for="(m, j) in record.messages" :key="j" class="text">
            {{ m.role }}: {{ m.content }}
          </p>
          <p class="text">Ответ: {{ record.answer?.reply }}</p>
        </article>
        <div class="checks">
          <NCheckbox v-model:checked="reviewed">Я проверил содержание датасета</NCheckbox
          ><NCheckbox v-model:checked="anonymized">Персональные данные удалены</NCheckbox
          ><NCheckbox v-model:checked="servicesOnly">Только разрешённые услуги</NCheckbox>
        </div>
        <NButton
          :disabled="busy || !reviewed || !anonymized || !servicesOnly"
          @click="
            () => {
              mutate(`datasets/${selected!.id}/approve`, {
                reviewed,
                personal_data_removed: anonymized,
                authorized_services_only: servicesOnly,
              })
            }
          "
          >Одобрить датасет</NButton
        >
      </div>
    </section>
    <section v-if="tab === 6" class="panel">
      <h2>Обучение</h2>
      <NAlert :type="resources.worker_online ? 'info' : 'warning'"
        >{{
          resources.worker_online ? 'Обучающий сервер подключён' : 'Обучающий сервер не подключён'
        }}. Полный цикл обучения требует серверной приёмки.</NAlert
      >
      <div v-if="resources.resources">
        <p>Свободные ресурсы: {{ resources.resources }}</p>
        <p v-for="(profile, key) in resources.profiles" :key="key">{{ key }}: {{ profile }}</p>
      </div>
      <div class="form-grid">
        <label
          >Одобренный датасет<NSelect
            v-model:value="datasetId"
            :options="
              datasets.filter((d) => d.approved).map((d) => ({ label: d.name, value: d.id }))
            " /></label
        ><label
          >Исходная модель<NSelect
            v-model:value="baseModel"
            :options="
              ['t-tech/T-lite-it-2.1', 't-tech/T-pro-it-2.1'].map((value) => ({
                label: value,
                value,
              }))
            " /></label
        ><label>Эпохи<NInputNumber v-model:value="epochs" :min="0.1" :max="3" :step="0.1" /></label
        ><label
          >Длина примера<NInputNumber v-model:value="maxLength" :min="256" :max="2048" /></label
        ><label
          >Скорость обучения<NInputNumber
            v-model:value="rate"
            :min="0.000001"
            :max="0.0003"
            :step="0.00001" /></label
        ><label>Seed<NInputNumber v-model:value="seed" /></label>
      </div>
      <NButton
        type="primary"
        :disabled="busy || !resources.worker_online || !baseModel || !datasetId"
        @click="
          () => {
            mutate('training/jobs', {
              dataset_id: datasetId,
              base_model: baseModel,
              epochs,
              max_length: maxLength,
              learning_rate: rate,
              seed,
            })
          }
        "
        >Запустить обучение</NButton
      >
      <article v-for="item in items" :key="item.id">
        <h3>{{ item.id }}</h3>
        <NTag>{{ labels[item.status] || item.status }}</NTag>
        <p>{{ item.error }}</p>
        <p>{{ item.metrics }}</p>
        <div class="actions">
          <NButton
            @click="
              () => {
                run(async () => {
                  selected = await get(`service/training/jobs/${item.id}`)
                  logJob = item.id
                  logCursor = 0
                  logs = []
                  await refresh()
                })
              }
            "
            >Показать журнал</NButton
          ><NButton
            v-if="['queued', 'running'].includes(item.status)"
            :disabled="busy"
            @click="
              () => {
                mutate(`training/jobs/${item.id}/cancel`)
              }
            "
            >Запросить отмену</NButton
          >
        </div>
      </article>
      <div v-if="selected">
        <h3>Задача {{ selected!.id }}</h3>
        <p>Модель: {{ selected.config?.base_model }}</p>
        <p>Метрики: {{ selected.metrics || 'Пока нет' }}</p>
        <p v-for="entry in logs" :key="entry.id">
          {{ entry.event.stage || entry.event.type }} · {{ entry.event.step || '' }}
          {{ entry.event.total_steps ? '/ ' + entry.event.total_steps : '' }}
          {{ entry.event.loss != null ? 'loss: ' + entry.event.loss : '' }}
          {{ entry.event.message || '' }}
        </p>
      </div>
    </section>
    <section v-if="tab === 7" class="panel">
      <h2>Версии моделей</h2>
      <p>Рабочая модель: {{ connection.model }}</p>
      <p>Обучение создаёт кандидата. Тест, одобрение и активация выполняются отдельно.</p>
      <article v-for="item in items" :key="item.id">
        <h3>{{ item.model }}</h3>
        <p>{{ item.metrics }}</p>
        <NTag>{{ item.evaluated ? 'Качество одобрено' : 'Требуется тест и проверка' }}</NTag>
        <div class="actions">
          <NButton
            @click="
              () => {
                candidateId = item.id
                tab = 3
              }
            "
            >Проверить в чате</NButton
          ><NButton
            @click="
              () => {
                selected = item
                qualityReviewed = false
              }
            "
            >Оценить качество</NButton
          ><NButton
            :disabled="busy || !item.evaluated"
            @click="
              () => {
                mutate(`model-versions/${item.id}/activate`)
              }
            "
            >Активировать</NButton
          >
        </div>
      </article>
      <div v-if="selected">
        <NCheckbox v-model:checked="qualityReviewed"
          >Я проверил реальные ответы этой версии</NCheckbox
        ><NButton
          :disabled="busy || !qualityReviewed"
          @click="
            () => {
              mutate(`model-versions/${selected!.id}/approve`, {
                quality_reviewed: qualityReviewed,
              })
            }
          "
          >Одобрить модель</NButton
        >
      </div>
      <p>Откат конкретной активации доступен в журнале CRM.</p>
    </section>
    <section v-if="tab === 8" class="panel">
      <h2>Журнал CRM</h2>
      <article v-for="item in items" :key="item.id">
        <h3>{{ item.action }}</h3>
        <p>
          {{ item.created_at }} · сотрудник #{{ item.actor_id }} ·
          {{ labels[item.status] || item.status }}
        </p>
        <p>{{ item.data }}</p>
        <NButton
          v-if="item.data.activation_id && !item.action.endsWith('/rollback')"
          :disabled="busy"
          @click="
            () => {
              mutate(`model-activations/${item.data.activation_id}/rollback`)
            }
          "
          >Откатить эту активацию</NButton
        >
      </article>
    </section>
  </main>
</template>

<style scoped>
.ai-page {
  max-width: 1120px;
  margin: auto;
  padding: 24px;
  display: grid;
  gap: 20px;
  min-width: 0;
  color: var(--app-text);
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
}
h1 {
  font-size: 30px;
  margin: 4px 0;
}
h2 {
  margin: 0 0 8px;
}
p {
  overflow-wrap: anywhere;
}
.eyebrow {
  font-size: 11px;
  letter-spacing: 0.12em;
  opacity: 0.6;
}
nav,
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
nav button {
  background: var(--app-surface);
  color: inherit;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  padding: 10px 14px;
  cursor: pointer;
}
nav button.active {
  background: #4468dc;
  color: #fff;
  border-color: #4468dc;
}
.panel {
  padding: 24px;
  border: 1px solid var(--app-border);
  border-radius: 16px;
  background: var(--app-surface);
  display: grid;
  gap: 16px;
  min-width: 0;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
label {
  display: grid;
  gap: 7px;
}
article {
  border-top: 1px solid var(--app-border);
  padding: 18px 0;
  min-width: 0;
}
h3 {
  margin: 0 0 12px;
}
.text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.answer {
  border-left: 3px solid #4468dc;
  padding-left: 14px;
}
.checks,
.editor {
  display: grid;
  gap: 12px;
}
.upload {
  border: 1px dashed var(--app-border);
  padding: 16px;
  border-radius: 10px;
}
input[type='file'] {
  max-width: 100%;
}
@media (max-width: 640px) {
  .ai-page {
    padding: 12px;
  }
  .panel {
    padding: 16px;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
  header {
    align-items: flex-start;
  }
  h1 {
    font-size: 24px;
  }
}
.muted {
  color: var(--app-text-muted);
  margin: 0;
  line-height: 1.6;
}
.advanced {
  border: 1px solid var(--app-border);
  border-radius: 12px;
  padding: 16px;
  min-width: 0;
}
summary {
  cursor: pointer;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.advanced[open] > * + * {
  margin-top: 18px;
}
.prompt-steps {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 24px;
  color: var(--app-text-muted);
  font-size: 13px;
}
.prompt-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
}
.prompt-footer p {
  flex: 1 1 260px;
}
.version-heading {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}
.version-heading h3 {
  margin: 0;
  overflow-wrap: anywhere;
}
.prompt-version {
  border: 1px solid var(--app-border);
  border-radius: 12px;
  padding: 18px;
  display: grid;
  gap: 16px;
}
.prompt-version.is-active {
  border-color: var(--app-accent);
}
.prompt-panel :deep(textarea) {
  line-height: 1.75;
}
</style>
