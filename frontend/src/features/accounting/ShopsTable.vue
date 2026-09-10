<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NInput, NDatePicker, useMessage } from 'naive-ui'
import { http, AppError } from '@/shared/api/http'
import type { AccountingUnitOwnerRow } from './types'
import { shopTableFields } from './shopFields'
defineProps<{ rows: AccountingUnitOwnerRow[] }>()
const emit = defineEmits<{ saved: [] }>()
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
  <div class="shops-table" tabindex="0" aria-label="Реестр лавок">
    <table>
      <thead>
        <tr>
          <th v-for="field in shopTableFields" :key="field[0]" scope="col">{{ field[1] }}</th>
          <th scope="col">Действия</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="row in rows" :key="row.unit_id">
          <tr>
            <td v-for="field in shopTableFields" :key="field[0]">
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
            <td :colspan="shopTableFields.length + 1">
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
</template>
<style scoped>
.shops-table {
  overflow: auto;
  max-height: 70vh;
  border: 1px solid var(--border-color, #e0e0e6);
  border-radius: 6px;
}
table {
  border-collapse: separate;
  border-spacing: 0;
  width: 100%;
  font-size: 13px;
}
th,
td {
  padding: 8px 12px;
  min-width: 140px;
  max-width: 280px;
  border-right: 1px solid var(--border-color, #e0e0e6);
  border-bottom: 1px solid var(--border-color, #e0e0e6);
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
}
th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--card-color, #fff);
  white-space: nowrap;
  font-weight: 600;
}
th:first-child,
td:first-child {
  position: sticky;
  left: 0;
  background: var(--card-color, #fff);
  min-width: 200px;
  z-index: 1;
}
th:first-child {
  z-index: 3;
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
}
.shop-name:hover {
  text-decoration: underline;
}
.actions {
  min-width: 220px;
  white-space: nowrap;
  position: sticky;
  right: 0;
  background: var(--card-color, #fff);
  z-index: 1;
}
th:last-child {
  position: sticky;
  right: 0;
  z-index: 3;
}
td :deep(.n-date-picker) {
  min-width: 160px;
}
.details td {
  position: static;
}
.details-content {
  position: sticky;
  left: 12px;
  width: min(900px, 75vw);
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  color: var(--text-color-2, #666);
}
</style>
