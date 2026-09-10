<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { shopTableFields } from './shopFields'
import { NButton, NDatePicker, NForm, NFormItem, NInput, NModal, NSpin, useMessage } from 'naive-ui'
import { http, AppError } from '@/shared/api/http'
import type { AccountingUnitOwnerRow } from './types'
import type { LawyerShop } from '@/features/lawyer-registry/types'

const props = defineProps<{ unit: AccountingUnitOwnerRow }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const message = useMessage()
const loading = ref(true)
const saving = ref(false)
const failed = ref(false)
const form = ref<Record<string, string | null>>({})
let initial: Record<string, string | null> = {}
const allFields = [
  ['name', 'Наименование'],
  ['director_name', 'Директор'],
  ['registered_at', 'Дата регистрации', 'date'],
  ['received_at', 'Дата приёма', 'date'],
  ['dirovod', 'Дировод'],
  ['fns', 'ФНС'],
  ['sale_priority', 'Категория'],
  ['company_status', 'Статус'],
  ['ecsp_status', 'ЭЦП'],
  ['ecsp_until', 'ЭЦП действует до', 'date'],
  ['banks', 'Банки'],
  ['accounts_status', 'Счета'],
  ['sbis', 'СБИС'],
  ['edo_until', 'ЭДО действует до', 'date'],
  ['edo_id', 'ЭДО ID'],
  ['purchased_at', 'Дата покупки', 'date'],
  ['failed_at', 'Дата слёта', 'date'],
  ['failure_reason', 'Причина слёта'],
  ['unreliable', 'Недостоверность'],
  ['treatment_status', 'Работа по тикетам'],
  ['zsk', 'ЗСК'],
  ['manager', 'Менеджер'],
  ['phone', 'Телефон'],
  ['telegram', 'Telegram'],
  ['comment', 'Комментарий'],
] as const
const fields = shopTableFields.filter(
  (field) => field[0] !== 'inn' && field[0] !== 'accountant_full_name',
)
const extraFields = allFields.filter((field) => !fields.some((main) => main[0] === field[0]))

async function load() {
  loading.value = true
  failed.value = false
  try {
    const { data } = await http.get<LawyerShop | null>(
      `/accounting/units/${props.unit.unit_id}/card`,
    )
    form.value = Object.fromEntries(
      allFields.map(([key]) => [
        key,
        data?.[key] ?? (key === 'name' ? props.unit.name || props.unit.inn : null),
      ]),
    )
    initial = { ...form.value }
  } catch (err) {
    failed.value = true
    message.error(err instanceof AppError ? err.message : 'Не удалось загрузить лавку')
  } finally {
    loading.value = false
  }
}
async function save() {
  if (!form.value.name?.trim()) {
    message.error('Укажите название лавки')
    return
  }
  const patch = Object.fromEntries(
    Object.entries(form.value)
      .map(([key, value]) => [key, value?.trim() || null])
      .filter(([key, value]) => initial[key as string] !== value),
  )
  if (!Object.keys(patch).length) {
    emit('close')
    return
  }
  saving.value = true
  try {
    await http.patch(`/accounting/units/${props.unit.unit_id}/card`, patch)
    message.success('Лавка сохранена')
    emit('saved')
    emit('close')
  } catch (err) {
    message.error(err instanceof AppError ? err.message : 'Не удалось сохранить лавку')
  } finally {
    saving.value = false
  }
}
onMounted(load)
</script>

<template>
  <NModal
    :show="true"
    preset="card"
    :title="`Лавка · ${unit.inn}`"
    style="width: 840px"
    :mask-closable="false"
    :closable="!saving"
    @close="emit('close')"
  >
    <NSpin :show="loading">
      <NButton v-if="failed" @click="load">Повторить загрузку</NButton>
      <NForm v-else-if="!loading" label-placement="top" @submit.prevent="save">
        <div class="shop-form">
          <NFormItem v-for="field in fields" :key="field[0]" :label="field[1]">
            <NDatePicker
              v-if="field[2] === 'date'"
              v-model:formatted-value="form[field[0]]"
              value-format="yyyy-MM-dd"
              type="date"
              clearable
              :disabled="saving"
            />
            <NInput
              v-else
              v-model:value="form[field[0]]"
              :type="field[0] === 'comment' ? 'textarea' : 'text'"
              :disabled="saving"
            />
          </NFormItem>
        </div>
        <NFormItem label="Бухгалтер">{{ unit.accountant_full_name || 'Не назначен' }}</NFormItem>
        <details class="shop-extra">
          <summary>Дополнительные данные</summary>
          <div class="shop-form">
            <NFormItem v-for="field in extraFields" :key="field[0]" :label="field[1]">
              <NDatePicker
                v-if="field[2] === 'date'"
                v-model:formatted-value="form[field[0]]"
                value-format="yyyy-MM-dd"
                type="date"
                clearable
                :disabled="saving"
              />
              <NInput v-else v-model:value="form[field[0]]" :disabled="saving" />
            </NFormItem>
          </div>
        </details>
      </NForm>
    </NSpin>
    <template #footer>
      <div class="shop-actions">
        <NButton :disabled="saving" @click="emit('close')">Отмена</NButton
        ><NButton type="primary" :loading="saving" :disabled="loading || failed" @click="save"
          >Сохранить</NButton
        >
      </div>
    </template>
  </NModal>
</template>

<style scoped>
.shop-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 20px;
}
.shop-form :deep(.n-date-picker) {
  width: 100%;
}
.shop-extra summary {
  cursor: pointer;
  padding: 12px 0;
  color: var(--text-color-2, #666);
}
.shop-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
@media (max-width: 600px) {
  .shop-form {
    grid-template-columns: 1fr;
  }
}
</style>
