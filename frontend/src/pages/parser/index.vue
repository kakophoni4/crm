<script setup lang="ts">
import type { DataTableColumns, SelectOption, UploadCustomRequestOptions } from 'naive-ui'
import {
  NButton,
  NDataTable,
  NEmpty,
  NInput,
  NSelect,
  NSpin,
  NTag,
  NUpload,
  useDialog,
  useMessage,
} from 'naive-ui'
import { FileSpreadsheet, RefreshCw, Trash2 } from 'lucide-vue-next'
import { computed, h, onMounted, ref } from 'vue'

import {
  deleteLavokLot,
  ingestLavokXlsx,
  listLavokLots,
  patchLavokLot,
} from '@/features/lavok-parser/api'
import {
  LAVOK_MARK_OPTIONS,
  type LavokParserLot,
} from '@/features/lavok-parser/types'
import { AppError } from '@/shared/api/http'
import AppCard from '@/shared/ui/AppCard.vue'

const message = useMessage()
const dialog = useDialog()

const loading = ref(false)
const ingesting = ref(false)
const rows = ref<LavokParserLot[]>([])
const total = ref(0)
const sheetDates = ref<string[]>([])
const sheetDate = ref<string | null>(null)
const search = ref('')
const expandedIds = ref<number[]>([])

const dateOptions = computed<SelectOption[]>(() =>
  sheetDates.value.map((value) => ({ label: formatSheetDate(value), value })),
)

function formatSheetDate(value: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split('-')
    return `${day}.${month}.${year}`
  }
  return value
}

function markLabel(mark: string): string {
  return LAVOK_MARK_OPTIONS.find((item) => item.value === mark)?.label ?? mark
}

function markType(mark: string): 'default' | 'info' | 'success' | 'warning' {
  if (mark === 'taking') return 'success'
  if (mark === 'watching') return 'info'
  if (mark === 'skip') return 'warning'
  return 'default'
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listLavokLots({
      sheet_date: sheetDate.value,
      q: search.value.trim() || undefined,
      limit: 500,
    })
    rows.value = data.items
    total.value = data.total
    sheetDates.value = data.sheet_dates
    if (data.sheet_date && sheetDate.value == null) {
      sheetDate.value = data.sheet_date
    }
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить парсер')
  } finally {
    loading.value = false
  }
}

async function onIngest({ file, onFinish, onError }: UploadCustomRequestOptions): Promise<void> {
  const raw = file.file
  if (!raw) {
    onError()
    return
  }
  ingesting.value = true
  try {
    const result = await ingestLavokXlsx(raw)
    message.success(`Загружено: ${result.created} новых, ${result.updated} обновлено`)
    sheetDate.value = null
    await load()
    onFinish()
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить xlsx')
    onError()
  } finally {
    ingesting.value = false
  }
}

async function onMark(row: LavokParserLot, mark: string): Promise<void> {
  try {
    const updated = await patchLavokLot(row.id, { mark })
    rows.value = rows.value.map((item) => (item.id === row.id ? updated : item))
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить отметку')
  }
}

function onDelete(row: LavokParserLot): void {
  dialog.warning({
    title: 'Удалить строку?',
    content: `${row.name || row.inn} пропадёт из таблицы.`,
    positiveText: 'Удалить',
    negativeText: 'Отмена',
    onPositiveClick: async () => {
      try {
        await deleteLavokLot(row.id)
        rows.value = rows.value.filter((item) => item.id !== row.id)
        total.value = Math.max(0, total.value - 1)
        message.success('Удалено')
      } catch (err) {
        message.error(err instanceof AppError ? err.message : 'Не удалось удалить')
      }
    },
  })
}

function toggleSummary(id: number): void {
  if (expandedIds.value.includes(id)) {
    expandedIds.value = expandedIds.value.filter((item) => item !== id)
  } else {
    expandedIds.value = [...expandedIds.value, id]
  }
}

const columns: DataTableColumns<LavokParserLot> = [
  {
    title: 'Название',
    key: 'name',
    minWidth: 180,
    ellipsis: { tooltip: true },
    render: (row) => row.name || '—',
  },
  { title: 'ИНН', key: 'inn', width: 130 },
  { title: 'Цена', key: 'price', width: 100, render: (row) => row.price || '—' },
  { title: 'Балл', key: 'score', width: 70, render: (row) => row.score || '—' },
  { title: 'Налог', key: 'tax', width: 90, ellipsis: { tooltip: true }, render: (row) => row.tax || '—' },
  {
    title: 'ЕГРЮЛ',
    key: 'egrul_status',
    width: 120,
    ellipsis: { tooltip: true },
    render: (row) => row.egrul_status || '—',
  },
  {
    title: 'Итог',
    key: 'summary',
    minWidth: 160,
    render: (row) =>
      h(
        NButton,
        { size: 'tiny', quaternary: true, onClick: () => toggleSummary(row.id) },
        { default: () => (expandedIds.value.includes(row.id) ? 'Скрыть' : 'Открыть') },
      ),
  },
  {
    title: 'Отметка',
    key: 'mark',
    width: 170,
    render: (row) =>
      h(NSelect, {
        value: row.mark,
        size: 'small',
        options: LAVOK_MARK_OPTIONS,
        onUpdateValue: (value: string) => onMark(row, value),
      }),
  },
  {
    title: '',
    key: 'actions',
    width: 90,
    render: (row) =>
      h(
        NButton,
        { size: 'tiny', tertiary: true, type: 'error', onClick: () => onDelete(row) },
        {
          icon: () => h(Trash2, { size: 14 }),
          default: () => 'Удалить',
        },
      ),
  },
]

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="parser-page">
    <header class="parser-page__header">
      <h1 class="parser-page__title">
        <FileSpreadsheet :size="22" />
        Парсер лавок
      </h1>
      <div class="parser-page__header-actions">
        <NUpload
          :show-file-list="false"
          accept=".xlsx"
          :disabled="ingesting"
          :custom-request="onIngest"
        >
          <NButton type="primary" :loading="ingesting">Загрузить xlsx</NButton>
        </NUpload>
        <NButton :loading="loading" @click="load">
          <template #icon><RefreshCw :size="16" /></template>
          Обновить
        </NButton>
      </div>
    </header>

    <AppCard>
      <div class="parser-page__filters">
        <NSelect
          v-model:value="sheetDate"
          :options="dateOptions"
          placeholder="Дата листа"
          style="min-width: 180px"
          @update:value="load"
        />
        <NInput
          v-model:value="search"
          clearable
          placeholder="ИНН или название"
          style="min-width: 240px"
          @keyup.enter="load"
        />
        <NButton @click="load">Найти</NButton>
        <NTag :bordered="false">{{ total }} строк</NTag>
      </div>
      <NSpin :show="loading && rows.length === 0">
        <NEmpty v-if="!loading && rows.length === 0" description="Нет строк парсера" />
        <NDataTable
          v-else
          :columns="columns"
          :data="rows"
          :row-key="(row: LavokParserLot) => row.id"
          :bordered="false"
          :single-line="false"
          size="small"
          :scroll-x="1180"
        />
      </NSpin>
      <div v-if="expandedIds.length" class="parser-page__summaries">
        <article
          v-for="row in rows.filter((item) => expandedIds.includes(item.id))"
          :key="row.id"
          class="parser-page__summary"
        >
          <header>
            <strong>{{ row.name || row.inn }}</strong>
            <NTag size="small" :type="markType(row.mark)" :bordered="false">
              {{ markLabel(row.mark) }}
            </NTag>
            <a v-if="row.link" :href="row.link" target="_blank" rel="noreferrer">Пост</a>
          </header>
          <p>{{ row.summary || 'Нет текста «Итог»' }}</p>
        </article>
      </div>
    </AppCard>
  </div>
</template>

<style scoped>
.parser-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.parser-page__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.parser-page__title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}

.parser-page__header-actions,
.parser-page__filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.parser-page__filters {
  margin-bottom: 12px;
}

.parser-page__summaries {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.parser-page__summary {
  padding: 12px 14px;
  border: 1px solid var(--app-border);
  border-radius: 10px;
  background: var(--app-surface-muted, transparent);
}

.parser-page__summary header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.parser-page__summary p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.45;
}
</style>
