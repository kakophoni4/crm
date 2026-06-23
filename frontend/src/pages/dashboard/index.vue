<script setup lang="ts">
import { CheckCircle2, Clock, LayoutGrid, MessageSquare, UserPlus, XCircle } from 'lucide-vue-next'
import { NAlert, NDataTable, NIcon, NSpin } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { computed, h, onMounted, ref } from 'vue'

import { getCrmDashboardSummary } from '@/features/leads/api'
import type { CrmDashboardSummary, OperatorDashboardKpi, PipelineStatusCount } from '@/features/leads/types'
import AppCard from '@/shared/ui/AppCard.vue'

const loading = ref(true)
const error = ref<string | null>(null)
const summary = ref<CrmDashboardSummary | null>(null)

const pipelineRows = computed(() => summary.value?.by_pipeline_status ?? [])
const operatorRows = computed(() => summary.value?.by_operator ?? [])

const pipelineMax = computed(() => {
  const rows = pipelineRows.value
  if (!rows.length) return 1
  return Math.max(...rows.map((row) => row.count), 1)
})

function pipelineBarWidth(row: PipelineStatusCount): string {
  const pct = Math.round((row.count / pipelineMax.value) * 100)
  return `${Math.max(pct, row.count > 0 ? 6 : 0)}%`
}

function formatResponseMinutes(minutes: number | null | undefined): string {
  if (minutes == null || !Number.isFinite(minutes)) return '—'
  if (minutes < 1) return '< 1 мин'
  if (minutes < 60) return `${Math.round(minutes)} мин`
  const hours = Math.floor(minutes / 60)
  const mins = Math.round(minutes % 60)
  return mins > 0 ? `${hours} ч ${mins} мин` : `${hours} ч`
}

const operatorColumns = computed<DataTableColumns<OperatorDashboardKpi>>(() => [
  { title: 'Сотрудник', key: 'display_name', minWidth: 140, ellipsis: { tooltip: true } },
  {
    title: 'Чатов сегодня',
    key: 'chats_today_count',
    width: 118,
    align: 'right',
  },
  {
    title: 'Ср. ответ',
    key: 'avg_response_minutes',
    width: 108,
    align: 'right',
    render: (row) => formatResponseMinutes(row.avg_response_minutes),
  },
  {
    title: 'Успешных',
    key: 'closed_won_today_count',
    width: 96,
    align: 'right',
    render: (row) =>
      h('span', { class: 'dashboard-team__won' }, String(row.closed_won_today_count)),
  },
  {
    title: 'Неуспешных',
    key: 'closed_lost_today_count',
    width: 108,
    align: 'right',
    render: (row) =>
      h('span', { class: 'dashboard-team__lost' }, String(row.closed_lost_today_count)),
  },
  {
    title: 'Открытых сделок',
    key: 'open_leads_count',
    width: 124,
    align: 'right',
  },
])

const kpiItems = computed(() => {
  const s = summary.value
  return [
    {
      key: 'chats',
      label: 'Чатов сегодня',
      value: String(s?.chats_today_count ?? 0),
      valueKind: 'num' as const,
      icon: MessageSquare,
      tone: 'default' as const,
    },
    {
      key: 'response',
      label: 'Среднее время ответа',
      value: formatResponseMinutes(s?.avg_response_minutes),
      valueKind: 'text' as const,
      icon: Clock,
      tone: 'default' as const,
    },
    {
      key: 'won',
      label: 'Успешных продаж',
      value: String(s?.closed_won_today_count ?? 0),
      valueKind: 'num' as const,
      icon: CheckCircle2,
      tone: 'success' as const,
    },
    {
      key: 'lost',
      label: 'Неуспешных продаж',
      value: String(s?.closed_lost_today_count ?? 0),
      valueKind: 'num' as const,
      icon: XCircle,
      tone: 'danger' as const,
    },
    {
      key: 'clients',
      label: 'Новых клиентов',
      value: String(s?.new_clients_today_count ?? 0),
      valueKind: 'num' as const,
      icon: UserPlus,
      tone: 'default' as const,
    },
  ]
})

onMounted(async () => {
  try {
    summary.value = await getCrmDashboardSummary()
  } catch {
    error.value = 'Не удалось загрузить сводку ХУИтРИКС'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="dashboard-page">
    <header class="dashboard-page__hero">
      <div class="dashboard-page__hero-text">
        <h1 class="dashboard-page__title">Дашборд</h1>
      </div>
      <div class="dashboard-page__hero-badge" aria-hidden="true">
        <NIcon :size="20"><LayoutGrid /></NIcon>
      </div>
    </header>

    <NAlert v-if="error" type="error" :bordered="false" class="dashboard-page__alert">
      {{ error }}
    </NAlert>

    <NSpin v-else :show="loading">
      <section class="dashboard-section" aria-labelledby="dashboard-kpi-heading">
        <h2 id="dashboard-kpi-heading" class="dashboard-section__title">Сводка</h2>
        <ul class="dashboard-kpi">
          <li v-for="item in kpiItems" :key="item.key" class="dashboard-kpi__item">
            <article
              class="dashboard-kpi__card"
              :class="{
                'dashboard-kpi__card--success': item.tone === 'success',
                'dashboard-kpi__card--danger': item.tone === 'danger',
              }"
            >
              <div
                class="dashboard-kpi__icon"
                :class="{
                  'dashboard-kpi__icon--success': item.tone === 'success',
                  'dashboard-kpi__icon--danger': item.tone === 'danger',
                }"
                aria-hidden="true"
              >
                <NIcon :size="20"><component :is="item.icon" /></NIcon>
              </div>
              <div class="dashboard-kpi__body">
                <span class="dashboard-kpi__label">{{ item.label }}</span>
                <span
                  class="dashboard-kpi__value"
                  :class="{ 'dashboard-kpi__value--text': item.valueKind === 'text' }"
                >
                  {{ item.value }}
                </span>
              </div>
            </article>
          </li>
        </ul>
      </section>

      <section v-if="operatorRows.length" class="dashboard-section" aria-labelledby="dashboard-team-heading">
        <h2 id="dashboard-team-heading" class="dashboard-section__title">Команда</h2>
        <AppCard class="dashboard-team">
          <template #header>
            <h3 class="dashboard-card-heading">KPI по сотрудникам отдела</h3>
          </template>
          <div class="dashboard-table-wrap">
            <NDataTable
              class="dashboard-table"
              :columns="operatorColumns"
              :data="operatorRows"
              :bordered="false"
              :single-line="false"
              striped
              size="small"
              :row-key="(row: OperatorDashboardKpi) => row.user_id"
            />
          </div>
        </AppCard>
      </section>

      <section class="dashboard-section" aria-labelledby="dashboard-pipeline-heading">
        <h2 id="dashboard-pipeline-heading" class="dashboard-section__title">Воронка</h2>
        <AppCard class="dashboard-pipeline">
          <template #header>
            <h3 class="dashboard-card-heading">Активные сделки по этапам</h3>
          </template>
          <p v-if="!pipelineRows.length" class="dashboard-pipeline__empty">
            Нет активных сделок в воронке
          </p>
          <ul v-else class="dashboard-pipeline__list">
            <li
              v-for="row in pipelineRows"
              :key="row.status_id"
              class="dashboard-pipeline__row"
            >
              <div class="dashboard-pipeline__row-inner">
                <div class="dashboard-pipeline__row-head">
                  <span class="dashboard-pipeline__label">{{ row.label }}</span>
                  <span class="dashboard-pipeline__count">{{ row.count }}</span>
                </div>
                <div class="dashboard-pipeline__track" role="presentation">
                  <div class="dashboard-pipeline__fill" :style="{ width: pipelineBarWidth(row) }" />
                </div>
              </div>
            </li>
          </ul>
        </AppCard>
      </section>
    </NSpin>
  </div>
</template>

<style scoped>
.dashboard-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 8px clamp(16px, 3vw, 28px) 40px;
}

.dashboard-page__hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 28px;
  padding-bottom: 22px;
  border-bottom: 1px solid var(--app-border);
}

.dashboard-page__hero-text {
  min-width: 0;
}

.dashboard-page__title {
  margin: 0;
  font-size: clamp(1.5rem, 2.2vw, 1.75rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.2;
}

.dashboard-page__hero-badge {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 12px;
  color: var(--app-accent, #58a6ff);
  background: color-mix(in srgb, var(--app-accent, #58a6ff) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--app-accent, #58a6ff) 28%, transparent);
}

.dashboard-page__alert {
  margin-bottom: 16px;
}

.dashboard-section {
  margin-bottom: 28px;
}

.dashboard-section:last-child {
  margin-bottom: 0;
}

.dashboard-section__title {
  margin: 0 0 12px;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--app-text-muted);
}

.dashboard-card-heading {
  margin: 0;
  font-size: 1.0625rem;
  font-weight: 600;
  letter-spacing: -0.01em;
}

/* KPI: одна ровная сетка на десктопе, без «висящей» карточки */
.dashboard-kpi {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin: 0;
  padding: 0;
  list-style: none;
}

@media (max-width: 1100px) {
  .dashboard-kpi {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .dashboard-kpi {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 420px) {
  .dashboard-kpi {
    grid-template-columns: 1fr;
  }
}

.dashboard-kpi__item {
  min-width: 0;
}

.dashboard-kpi__card {
  display: flex;
  align-items: stretch;
  gap: 12px;
  height: 100%;
  min-height: 104px;
  padding: 16px 16px 18px;
  border-radius: 14px;
  border: 1px solid var(--app-border);
  background: linear-gradient(
    165deg,
    color-mix(in srgb, var(--app-surface) 92%, var(--app-text) 4%) 0%,
    var(--app-surface) 100%
  );
  box-shadow: 0 1px 0 color-mix(in srgb, var(--app-text) 6%, transparent);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.dashboard-kpi__card:hover {
  border-color: color-mix(in srgb, var(--app-accent, #58a6ff) 35%, var(--app-border));
  box-shadow:
    0 1px 0 color-mix(in srgb, var(--app-text) 6%, transparent),
    0 0 0 1px color-mix(in srgb, var(--app-accent, #58a6ff) 12%, transparent);
}

.dashboard-kpi__card--success:hover {
  border-color: color-mix(in srgb, #3fb950 40%, var(--app-border));
  box-shadow:
    0 1px 0 color-mix(in srgb, var(--app-text) 6%, transparent),
    0 0 0 1px color-mix(in srgb, #3fb950 14%, transparent);
}

.dashboard-kpi__card--danger:hover {
  border-color: color-mix(in srgb, #f85149 40%, var(--app-border));
  box-shadow:
    0 1px 0 color-mix(in srgb, var(--app-text) 6%, transparent),
    0 0 0 1px color-mix(in srgb, #f85149 14%, transparent);
}

.dashboard-kpi__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  margin-top: 2px;
  border-radius: 11px;
  background: color-mix(in srgb, var(--app-accent, #58a6ff) 12%, transparent);
  color: var(--app-accent, #58a6ff);
}

.dashboard-kpi__icon--success {
  background: color-mix(in srgb, #3fb950 16%, transparent);
  color: #3fb950;
}

.dashboard-kpi__icon--danger {
  background: color-mix(in srgb, #f85149 16%, transparent);
  color: #f85149;
}

.dashboard-kpi__body {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.dashboard-kpi__label {
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1.35;
  color: var(--app-text-muted);
}

.dashboard-kpi__value {
  font-size: 1.625rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  line-height: 1.15;
  letter-spacing: -0.02em;
  color: var(--app-text);
}

.dashboard-kpi__value--text {
  font-size: 1.2rem;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.dashboard-team {
  padding: 0;
  overflow: hidden;
  border-radius: 14px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  box-shadow: 0 1px 0 color-mix(in srgb, var(--app-text) 5%, transparent);
}

.dashboard-team :deep(.app-card__header) {
  margin: 0;
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--app-border);
  background: color-mix(in srgb, var(--app-surface-elevated) 55%, var(--app-surface));
}

.dashboard-team :deep(.app-card__body) {
  padding: 0;
}

.dashboard-table-wrap {
  padding: 4px 0 8px;
}

.dashboard-table :deep(.n-data-table-th) {
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--app-text-muted);
}

.dashboard-table :deep(.n-data-table-td) {
  font-size: 0.875rem;
}

.dashboard-table :deep(.n-data-table-tr--striped .n-data-table-td) {
  background: color-mix(in srgb, var(--app-surface-elevated) 35%, transparent);
}

.dashboard-team__won {
  color: #3fb950;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.dashboard-team__lost {
  color: #f85149;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.dashboard-pipeline {
  padding: 0;
  overflow: hidden;
  border-radius: 14px;
  border: 1px solid var(--app-border);
  background: var(--app-surface);
  box-shadow: 0 1px 0 color-mix(in srgb, var(--app-text) 5%, transparent);
}

.dashboard-pipeline :deep(.app-card__header) {
  margin: 0;
  padding: 16px 20px 12px;
  border-bottom: 1px solid var(--app-border);
  background: color-mix(in srgb, var(--app-surface-elevated) 55%, var(--app-surface));
}

.dashboard-pipeline :deep(.app-card__body) {
  padding: 16px 18px 20px;
}

.dashboard-pipeline__empty {
  margin: 0;
  padding: 12px 4px 8px;
  color: var(--app-text-muted);
  font-size: 0.9375rem;
  text-align: center;
}

.dashboard-pipeline__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dashboard-pipeline__row-inner {
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--app-border) 80%, transparent);
  background: color-mix(in srgb, var(--app-surface-elevated) 40%, transparent);
}

.dashboard-pipeline__row-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.dashboard-pipeline__label {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--app-text);
}

.dashboard-pipeline__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 2rem;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 0.8125rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--app-text);
  background: color-mix(in srgb, var(--app-accent, #58a6ff) 16%, transparent);
  border: 1px solid color-mix(in srgb, var(--app-accent, #58a6ff) 28%, transparent);
}

.dashboard-pipeline__track {
  height: 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--app-text) 8%, transparent);
  overflow: hidden;
}

.dashboard-pipeline__fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--app-accent, #58a6ff) 88%, #fff) 0%,
    var(--app-accent, #58a6ff) 100%
  );
  transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1);
}
</style>
