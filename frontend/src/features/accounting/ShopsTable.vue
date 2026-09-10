<script setup lang="ts">
import { computed, ref } from 'vue'
import { NButton, NInput, NDatePicker, useMessage } from 'naive-ui'
import { http, AppError } from '@/shared/api/http'
import type { AccountingUnitOwnerRow } from './types'
import { shopTableFields } from './shopFields'
defineProps<{ rows: AccountingUnitOwnerRow[] }>()
const emit = defineEmits<{ saved: [] }>()
const groups = [
  {
    label: 'Основное',
    keys: [
      'director_name',
      'fns',
      'sale_priority',
      'company_status',
      'accountant_full_name',
      'comment',
    ],
  },
  { label: 'ЭЦП и ЭДО', keys: ['ecsp_status', 'accounts_status', 'sbis', 'edo_until', 'edo_id'] },
  {
    label: 'Даты и состояние',
    keys: [
      'registered_at',
      'received_at',
      'purchased_at',
      'dirovod',
      'failed_at',
      'failure_reason',
    ],
  },
]
const activeGroup = ref(0)
const visibleFields = computed(() =>
  shopTableFields.filter(
    ([key]) => key === 'name' || groups[activeGroup.value]!.keys.includes(key),
  ),
)
const expanded = ref<number | null>(null)
const editing = ref<number | null>(null)
const saving = ref(false)
const draft = ref<Record<string, string | null>>({})
let initial: Record<string, string | null> = {}
const message = useMessage()
function startEdit(row: AccountingUnitOwnerRow) {
  editing.value = row.unit_id
  draft.value = Object.fromEntries(
    shopTableFields
      .filter(([key]) => key !== 'inn' && key !== 'accountant_full_name')
      .map(([key]) => [
        key,
        key === 'name'
          ? row.name || row.inn
          : key === 'director_name'
            ? row.lawyer_director_name || null
            : (row.shop_fields?.[key] ?? null),
      ]),
  )
  initial = { ...draft.value }
}
async function saveRow(row: AccountingUnitOwnerRow) {
  if (!draft.value.name?.trim()) {
    message.error('Укажите название лавки')
    return
  }
  const patch = Object.fromEntries(
    Object.entries(draft.value)
      .map(([key, value]) => [key, value?.trim() || null])
      .filter(([key, value]) => initial[key as string] !== value),
  )
  if (!Object.keys(patch).length) {
    editing.value = null
    return
  }
  saving.value = true
  try {
    await http.patch(`/accounting/units/${row.unit_id}/card`, patch)
    editing.value = null
    emit('saved')
    message.success('Лавка сохранена')
  } catch (error) {
    message.error(error instanceof AppError ? error.message : 'Не удалось сохранить лавку')
  } finally {
    saving.value = false
  }
}

function value(row: AccountingUnitOwnerRow, key: string) {
  if (key === 'name') return row.name || row.inn
  if (key === 'inn') return row.inn
  if (key === 'director_name') return row.lawyer_director_name || '—'
  if (key === 'accountant_full_name') return row.accountant_full_name || '—'
  const result = row.shop_fields?.[key]
  return result && /^\d{4}-\d{2}-\d{2}$/.test(result)
    ? result.split('-').reverse().join('.')
    : result || '—'
}
</script>
<template>
  <div class="shops-registry">
    <div class="column-groups" role="group" aria-label="Группы колонок">
      <NButton
        v-for="(group, index) in groups"
        :key="group.label"
        size="small"
        :type="activeGroup === index ? 'primary' : 'default'"
        :aria-pressed="activeGroup === index"
        @click="activeGroup = index"
        >{{ group.label }}</NButton
      >
    </div>
    <div class="shops-table" tabindex="0" aria-label="Реестр лавок">
      <table>
        <thead>
          <tr>
            <th v-for="field in visibleFields" :key="field[0]" scope="col">
              {{ field[0] === 'name' ? 'Лавка / ИНН' : field[1] }}
            </th>
            <th scope="col">Действия</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in rows" :key="row.unit_id">
            <tr>
              <td v-for="field in visibleFields" :key="field[0]" :data-label="field[1]">
                <template
                  v-if="
                    editing === row.unit_id &&
                    field[0] !== 'inn' &&
                    field[0] !== 'accountant_full_name'
                  "
                >
                  <NDatePicker
                    v-if="field[2] === 'date'"
                    v-model:formatted-value="draft[field[0]]"
                    value-format="yyyy-MM-dd"
                    format="dd.MM.yyyy"
                    type="date"
                    clearable
                    size="small"
                    :disabled="saving"
                    :aria-label="field[1]"
                  />
                  <NInput
                    v-else
                    v-model:value="draft[field[0]]"
                    size="small"
                    placeholder=""
                    :disabled="saving"
                    :input-props="{ 'aria-label': field[1] }"
                  />
                </template>
                <button
                  v-else-if="field[0] === 'name'"
                  class="shop-name"
                  :disabled="editing !== null"
                  @click="startEdit(row)"
                >
                  {{ value(row, field[0]) }}
                </button>
                <span v-else>{{ value(row, field[0]) }}</span>
                <small v-if="field[0] === 'name'" class="shop-inn">{{ row.inn }}</small>
              </td>
              <td class="actions">
                <template v-if="editing === row.unit_id"
                  ><NButton size="small" type="primary" :loading="saving" @click="saveRow(row)"
                    >Сохранить</NButton
                  ><NButton size="small" :disabled="saving" @click="editing = null"
                    >Отмена</NButton
                  ></template
                >
                <template v-else
                  ><NButton size="small" :disabled="editing !== null" @click="startEdit(row)"
                    >Заполнить</NButton
                  ><NButton
                    size="small"
                    quaternary
                    :disabled="editing !== null"
                    :aria-expanded="expanded === row.unit_id"
                    @click="expanded = expanded === row.unit_id ? null : row.unit_id"
                    >Подробности</NButton
                  ></template
                >
              </td>
            </tr>
            <tr v-if="expanded === row.unit_id && editing === null" class="details">
              <td :colspan="visibleFields.length + 1">
                <div class="details-content">
                  <span
                    >Процент: {{ row.commission_rate_percent ?? '—' }} · Периоды:
                    {{ row.period_codes?.join(', ') || '—' }}</span
                  >
                  <slot name="actions" :row="row" />
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>
<style scoped>
.shops-registry {
  container-type: inline-size;
  min-width: 0;
  width: 100%;
}
.column-groups {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0;
}
.shops-table {
  max-height: 70vh;
  overflow-y: auto;
  border: 1px solid var(--border-color, #e0e0e6);
  border-radius: 6px;
}
table {
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
  width: 100%;
  font-size: 13px;
}
th,
td {
  padding: 8px;
  border-right: 1px solid var(--border-color, #e0e0e6);
  border-bottom: 1px solid var(--border-color, #e0e0e6);
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
  min-width: 0;
}
th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--card-color, #fff);
  font-weight: 600;
}
th:first-child {
  width: 16%;
}
th:last-child {
  width: 105px;
}
.shop-name {
  border: 0;
  padding: 0;
  background: none;
  color: inherit;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  text-align: left;
  overflow-wrap: anywhere;
  max-width: 100%;
}
.shop-name:hover {
  text-decoration: underline;
}
.shop-inn {
  display: block;
  margin-top: 4px;
  color: var(--text-color-2, #666);
  font-variant-numeric: tabular-nums;
}
.actions :deep(.n-button) {
  display: flex;
  width: 100%;
  margin-bottom: 4px;
}
td :deep(.n-date-picker),
td :deep(.n-input) {
  width: 100%;
  min-width: 0;
}
.details-content {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  min-width: 0;
  color: var(--text-color-2, #666);
}
.details-content :deep(.n-select) {
  min-width: 0 !important;
  max-width: 100%;
}
@container (max-width: 760px) {
  table,
  tbody {
    display: block;
  }
  thead {
    display: none;
  }
  tbody > tr {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    border-bottom: 2px solid var(--border-color, #e0e0e6);
  }
  td {
    display: block;
  }
  td::before {
    content: attr(data-label);
    display: block;
    font-size: 12px;
    color: var(--text-color-2, #666);
    margin-bottom: 4px;
  }
  td:first-child,
  td.actions,
  .details td {
    grid-column: 1 / -1;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .actions :deep(.n-button) {
    width: auto;
  }
  .actions::before,
  .details td::before {
    display: none;
  }
}
</style>
