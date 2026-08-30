<script setup lang="ts">
import type { DataTableColumns, SelectOption, UploadCustomRequestOptions } from 'naive-ui'
import {
  NButton,
  NDataTable,
  NEmpty,
  NInput,
  NModal,
  NSelect,
  NSpin,
  NTabPane,
  NTabs,
  NTag,
  NUpload,
  useDialog,
  useMessage,
} from 'naive-ui'
import { ExternalLink, FileSpreadsheet, RefreshCw, Star, Trash2 } from 'lucide-vue-next'
import { computed, h, onMounted, ref } from 'vue'

import {
  deleteLavokLot,
  ingestLavokXlsx,
  listLavokLots,
  patchLavokLot,
} from '@/features/lavok-parser/api'
import {
  LAVOK_FAVORITE_STATUS_OPTIONS,
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
const selected = ref<LavokParserLot | null>(null)
const activeTab = ref<'all' | 'favorites'>('all')
const statusFilter = ref<string | null>(null)

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

function formatPrice(value: string | null): string {
  if (!value) return '—'
  const num = Number(String(value).replace(/\s/g, '').replace(',', '.'))
  if (!Number.isFinite(num)) return value
  return `${new Intl.NumberFormat('ru-RU').format(num)} ₽`
}

const detailFields = computed(() => {
  const row = selected.value
  if (!row) return []
  return [
    { label: 'ИНН', value: row.inn },
    { label: 'Цена', value: formatPrice(row.price) },
    { label: 'Балл', value: row.score },
    { label: 'Налог', value: row.tax },
    { label: 'ЕГРЮЛ', value: row.egrul_status },
    { label: 'Регистрация', value: row.registered_at },
    { label: 'Источник', value: row.source },
    { label: 'Продавец', value: row.seller },
    { label: 'Адрес и директор', value: row.address_director },
    { label: 'Суды', value: row.courts },
    { label: 'Долги / ИЛ', value: row.debts },
    { label: 'Достоверность ЕГРЮЛ', value: row.egrul_reliability },
    { label: 'Банкротство', value: row.bankruptcy },
    { label: 'Обороты', value: row.turnover },
    { label: 'Отчётность', value: row.reporting },
    { label: 'Лизинг / залоги', value: row.leasing },
    { label: 'ЗСК', value: row.zsk },
    { label: 'Первое появление', value: row.first_seen },
  ].filter((item) => item.value && item.value !== '—')
})

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await listLavokLots({
      sheet_date: activeTab.value === 'favorites' ? undefined : sheetDate.value,
      q: search.value.trim() || undefined,
      mark: activeTab.value === 'favorites' ? statusFilter.value : undefined,
      favorite: activeTab.value === 'favorites',
      limit: 500,
    })
    rows.value = data.items
    total.value = data.total
    sheetDates.value = data.sheet_dates
    if (data.sheet_date && sheetDate.value == null) {
      sheetDate.value = data.sheet_date
    }
    if (selected.value) {
      selected.value = rows.value.find((item) => item.id === selected.value?.id) ?? selected.value
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

function replaceRow(updated: LavokParserLot): void {
  rows.value = rows.value.map((item) => (item.id === updated.id ? updated : item))
  if (selected.value?.id === updated.id) selected.value = updated
}

async function onMark(row: LavokParserLot, mark: string): Promise<void> {
  try {
    replaceRow(await patchLavokLot(row.id, { mark }))
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить статус')
  }
}

async function onToggleFavorite(row: LavokParserLot): Promise<void> {
  try {
    const next = !row.is_favorite
    const updated = await patchLavokLot(row.id, {
      is_favorite: next,
      mark: next && (row.mark === 'skip' || !row.mark) ? 'new' : undefined,
    })
    if (activeTab.value === 'favorites' && !updated.is_favorite) {
      rows.value = rows.value.filter((item) => item.id !== row.id)
      total.value = Math.max(0, total.value - 1)
      if (selected.value?.id === row.id) selected.value = null
    } else {
      replaceRow(updated)
    }
    message.success(next ? 'Перенесено в избранное' : 'Убрано из избранного')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось обновить избранное')
  }
}

async function onNote(row: LavokParserLot, note: string): Promise<void> {
  try {
    replaceRow(await patchLavokLot(row.id, { note: note.trim() || null }))
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить заметку')
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
        if (selected.value?.id === row.id) selected.value = null
        message.success('Удалено')
      } catch (err) {
        message.error(err instanceof AppError ? err.message : 'Не удалось удалить')
      }
    },
  })
}

const noteDraft = ref('')

function openLot(row: LavokParserLot): void {
  selected.value = row
  noteDraft.value = row.note ?? ''
}

async function saveNote(): Promise<void> {
  if (!selected.value) return
  const next = noteDraft.value.trim() || null
  if (next === (selected.value.note ?? null)) return
  await onNote(selected.value, noteDraft.value)
}

const columns = computed<DataTableColumns<LavokParserLot>>(() => [
  {
    title: 'Название',
    key: 'name',
    minWidth: 180,
    ellipsis: { tooltip: true },
    render: (row) => row.name || '—',
  },
  { title: 'ИНН', key: 'inn', width: 130 },
  { title: 'Цена', key: 'price', width: 110, render: (row) => formatPrice(row.price) },
  { title: 'Балл', key: 'score', width: 70, render: (row) => row.score || '—' },
  { title: 'Налог', key: 'tax', width: 90, ellipsis: { tooltip: true }, render: (row) => row.tax || '—' },
  {
    title: 'ЕГРЮЛ',
    key: 'egrul_status',
    width: 120,
    ellipsis: { tooltip: true },
    render: (row) => row.egrul_status || '—',
  },
  ...(activeTab.value === 'favorites'
    ? [
        {
          title: 'Статус',
          key: 'mark',
          width: 160,
          render: (row: LavokParserLot) =>
            h(NSelect, {
              value: row.mark === 'skip' ? 'new' : row.mark,
              size: 'small',
              options: LAVOK_FAVORITE_STATUS_OPTIONS,
              onClick: (event: MouseEvent) => event.stopPropagation(),
              onUpdateValue: (value: string) => onMark(row, value),
            }),
        },
      ]
    : []),
  {
    title: '',
    key: 'actions',
    width: activeTab.value === 'favorites' ? 160 : 200,
    render: (row) =>
      h('div', { style: 'display:flex;gap:6px' }, [
        h(
          NButton,
          {
            size: 'tiny',
            tertiary: true,
            type: row.is_favorite ? 'warning' : 'default',
            onClick: (event: MouseEvent) => {
              event.stopPropagation()
              void onToggleFavorite(row)
            },
          },
          {
            icon: () => h(Star, { size: 14 }),
            default: () => (row.is_favorite ? 'Убрать' : 'В избранное'),
          },
        ),
        h(
          NButton,
          {
            size: 'tiny',
            tertiary: true,
            type: 'error',
            onClick: (event: MouseEvent) => {
              event.stopPropagation()
              onDelete(row)
            },
          },
          {
            icon: () => h(Trash2, { size: 14 }),
            default: () => 'Удалить',
          },
        ),
      ]),
  },
])

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
      <NTabs v-model:value="activeTab" type="line" @update:value="load">
        <NTabPane name="all" tab="Все лавки" />
        <NTabPane name="favorites" tab="Избранное" />
      </NTabs>
      <div class="parser-page__filters">
        <NSelect
          v-if="activeTab === 'all'"
          v-model:value="sheetDate"
          :options="dateOptions"
          placeholder="Дата листа"
          style="min-width: 180px"
          @update:value="load"
        />
        <NSelect
          v-if="activeTab === 'favorites'"
          v-model:value="statusFilter"
          :options="LAVOK_FAVORITE_STATUS_OPTIONS"
          clearable
          placeholder="Статус"
          style="min-width: 160px"
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
        <span class="parser-page__hint">
          {{
            activeTab === 'favorites'
              ? 'Статусы: новая, смотрю, беру. Можно отфильтровать сверху.'
              : 'Перенесите лавку в избранное, чтобы вести её отдельно.'
          }}
        </span>
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
          :scroll-x="1100"
          :row-props="(row: LavokParserLot) => ({
            style: 'cursor: pointer',
            onClick: () => openLot(row),
          })"
        />
      </NSpin>
    </AppCard>

    <NModal
      :show="selected != null"
      preset="card"
      :title="selected?.name || selected?.inn || 'Лот'"
      style="width: min(760px, calc(100vw - 32px)); max-height: 88vh"
      @update:show="(open: boolean) => { if (!open) selected = null }"
    >
      <div v-if="selected" class="lot-card">
        <div class="lot-card__meta">
          <NTag size="small" :type="markType(selected.mark)" :bordered="false">
            {{ markLabel(selected.mark) }}
          </NTag>
          <span v-if="selected.score">Балл {{ selected.score }}</span>
          <span>{{ formatPrice(selected.price) }}</span>
          <span v-if="selected.inn">ИНН {{ selected.inn }}</span>
        </div>

        <section class="lot-card__summary">
          <h3>Итог</h3>
          <p>{{ selected.summary || 'Текста «Итог» нет' }}</p>
        </section>

        <dl class="lot-card__facts">
          <div v-for="item in detailFields" :key="item.label">
            <dt>{{ item.label }}</dt>
            <dd>{{ item.value }}</dd>
          </div>
        </dl>

        <section v-if="selected.companium" class="lot-card__block">
          <h3>Companium</h3>
          <p>{{ selected.companium }}</p>
        </section>

        <section class="lot-card__block">
          <h3>Заметка</h3>
          <NInput
            v-model:value="noteDraft"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 6 }"
            placeholder="Своя заметка по лоту"
            @blur="saveNote"
          />
        </section>

        <div class="lot-card__actions">
          <NButton
            :type="selected.is_favorite ? 'warning' : 'default'"
            @click="onToggleFavorite(selected)"
          >
            <template #icon><Star :size="16" /></template>
            {{ selected.is_favorite ? 'Убрать из избранного' : 'В избранное' }}
          </NButton>
          <NSelect
            v-if="selected.is_favorite"
            :value="selected.mark === 'skip' ? 'new' : selected.mark"
            :options="LAVOK_FAVORITE_STATUS_OPTIONS"
            style="width: 180px"
            @update:value="(value: string) => onMark(selected!, value)"
          />
          <NButton
            v-if="selected.link"
            tag="a"
            :href="selected.link"
            target="_blank"
            rel="noreferrer"
          >
            <template #icon><ExternalLink :size="16" /></template>
            Пост
          </NButton>
        </div>
      </div>
    </NModal>
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

.parser-page__hint {
  font-size: 0.85rem;
  color: var(--app-text-muted);
}

.lot-card {
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: auto;
  max-height: calc(88vh - 88px);
  padding-right: 4px;
}

.lot-card__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  color: var(--app-text-muted);
  font-size: 0.9rem;
}

.lot-card__summary,
.lot-card__block {
  padding: 14px 16px;
  border: 1px solid var(--app-border);
  border-radius: 12px;
  background: var(--app-surface-muted, transparent);
}

.lot-card h3 {
  margin: 0 0 8px;
  font-size: 0.8rem;
  font-weight: 650;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--app-text-muted);
}

.lot-card__summary p,
.lot-card__block p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.55;
  font-size: 0.98rem;
}

.lot-card__facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px 16px;
  margin: 0;
}

.lot-card__facts div {
  min-width: 0;
}

.lot-card__facts dt {
  font-size: 0.75rem;
  color: var(--app-text-muted);
  margin-bottom: 2px;
}

.lot-card__facts dd {
  margin: 0;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.lot-card__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
</style>
