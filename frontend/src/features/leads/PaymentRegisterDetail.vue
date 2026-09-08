<script setup lang="ts">
import { computed, ref } from 'vue'
import OrderOkvedField from './OrderOkvedField.vue'
import { NButton, NForm, NFormItem, NInput, NInputNumber, NTag, useMessage } from 'naive-ui'
import { http, AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'
import { formatOptPeriodLabel } from './order-fields'
import { groupPaymentShops } from './payment-register'
import type { OptPaymentRegisterItem } from './opt-types'

const props = defineProps<{ order: OptPaymentRegisterItem }>()
const emit = defineEmits<{ saved: [] }>()
const auth = useAuthStore()
const message = useMessage()
const shops = computed(() => groupPaymentShops(props.order))
const canEdit = computed(() => auth.user?.permissions.includes('contacts.update'))
const editorInn = ref<string | null>(null)
const saving = ref(false)
const form = ref({ rate: null as number | null, returned: 0 as number | null, comment: '' })
const money = (value: number) => `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value)} ₽`
const configured = computed(() => shops.value.every((shop) => shop.configured))
const beneficiaryTotal = computed(() => shops.value.reduce((n, shop) => n + shop.beneficiary, 0))
const returnedTotal = computed(() => shops.value.reduce((n, shop) => n + shop.returned, 0))

function edit(shop: ReturnType<typeof groupPaymentShops>[number]) {
  editorInn.value = shop.inn
  form.value = { rate: shop.rate, returned: shop.returned, comment: shop.comment }
}

async function save() {
  if (form.value.returned == null) { message.warning('Укажите выплаченную сумму, в том числе 0'); return }
  saving.value = true
  try {
    await http.put(`/leads/${props.order.lead_id}/opt-orders/${props.order.order_id}/settlements/${editorInn.value}`, {
      beneficiary_rate_percent: form.value.rate, beneficiary_paid_amount: form.value.returned,
      comment: form.value.comment || null,
    })
    editorInn.value = null
    message.success('Условия бенефициара сохранены')
    emit('saved')
  } catch (err) { message.error(err instanceof AppError ? err.message : 'Не удалось сохранить условия') }
  finally { saving.value = false }
}
</script>

<template>
  <div class="settlement">
    <div class="settlement__identity">
      <div><h3>{{ order.client_name || 'Имя клиента не указано' }}</h3><p>{{ order.client_shop_name || 'Название лавки клиента не указано' }}</p><p>ИНН {{ order.client_inn }}</p></div>
      <NTag :type="order.is_paid ? 'success' : 'warning'" :bordered="false">{{ order.is_paid ? 'Заявка оплачена' : 'Заявка не оплачена полностью' }}</NTag>
    </div>
    <dl class="settlement__meta">
      <div><dt>Сделка</dt><dd>№{{ order.lead_id }}</dd></div>
      <div><dt>Период</dt><dd>{{ order.period_code ? formatOptPeriodLabel(order.period_code) : 'Не указан' }}</dd></div>
      <div><dt>Менеджер</dt><dd>{{ order.manager_name || 'Не назначен' }}</dd></div>
      <div><dt>ОКВЭД покупателя</dt><dd><OrderOkvedField :lead-id="order.lead_id" :order-id="order.order_id" :value="order.client_okved" @saved="emit('saved')" /></dd></div>
    </dl>
    <dl class="settlement__metrics">
      <div><dt>Объём заявки</dt><dd>{{ money(order.volume) }}</dd></div>
      <div><dt>К оплате клиентом</dt><dd>{{ money(order.due_amount) }}</dd></div>
      <div><dt>Получено от клиента</dt><dd>{{ money(order.paid_amount) }}</dd></div>
      <div><dt>Осталось получить</dt><dd>{{ money(order.remaining_amount) }}</dd></div>
    </dl>

    <div class="settlement__heading"><h3>Лавки в заявке</h3><span>{{ shops.length }}</span></div>
    <section v-for="shop in shops" :key="shop.inn" class="settlement__shop">
      <div class="settlement__identity"><div><h4>{{ shop.name }}</h4><p>ИНН {{ shop.inn }} · документов: {{ shop.lines.length }}</p></div>
        <NButton v-if="canEdit" size="small" secondary :disabled="saving" @click="edit(shop)">{{ shop.configured ? 'Изменить условия' : 'Заполнить условия' }}</NButton>
      </div>
      <dl class="settlement__metrics">
        <div><dt>Объём по лавке</dt><dd>{{ money(shop.volume) }}</dd></div>
        <div><dt>Наша комиссия</dt><dd>{{ money(shop.due) }}</dd></div>
        <div><dt>Ставка бенефициара</dt><dd>{{ shop.mixedRates ? 'Разные ставки в документах' : shop.rate == null ? 'Не заполнена' : `${shop.rate}%` }}</dd></div>
        <div><dt>Начислено бенефициару</dt><dd>{{ shop.configured ? money(shop.beneficiary) : 'Укажите ставку' }}</dd></div>
        <div><dt>Выплачено бенефициару</dt><dd>{{ money(shop.returned) }}</dd></div>
        <div><dt>Плановая маржа</dt><dd>{{ shop.configured ? money(shop.due - shop.beneficiary) : 'Ожидает заполнения ставки' }}</dd></div>
      </dl>
      <p v-if="shop.comment" class="settlement__comment">{{ shop.comment }}</p>
      <NForm v-if="editorInn === shop.inn" class="settlement__form" label-placement="top" @submit.prevent="save">
        <p v-if="shop.mixedRates" class="settlement__hint">Сохранение установит одну ставку на все документы этой лавки в заявке.</p>
        <NFormItem label="Ставка бенефициара, %"><NInputNumber v-model:value="form.rate" :min="0" :max="100" :precision="2" clearable placeholder="Например, 0,5" :disabled="saving" /></NFormItem>
        <NFormItem label="Всего выплачено бенефициару, ₽"><NInputNumber v-model:value="form.returned" :min="0" :precision="2" placeholder="0, если ещё не платили" :disabled="saving" /></NFormItem>
        <NFormItem label="Комментарий к расчёту"><NInput v-model:value="form.comment" type="textarea" :maxlength="2000" :autosize="{ minRows: 2, maxRows: 5 }" :disabled="saving" placeholder="Условия, договорённости или пояснение" /></NFormItem>

        <div class="settlement__actions"><NButton :disabled="saving" @click="editorInn = null">Отмена</NButton><NButton type="primary" attr-type="submit" :loading="saving">Сохранить условия</NButton></div>
      </NForm>
    </section>
    <dl class="settlement__metrics">
      <div><dt>Плановая маржа заявки</dt><dd>{{ configured ? money(order.due_amount - beneficiaryTotal) : 'Заполните ставки всех лавок' }}</dd></div>
      <div><dt>Получено за вычетом выплат бенефициару</dt><dd>{{ money(order.paid_amount - returnedTotal) }}</dd></div>
    </dl>
  </div>
</template>

<style scoped>
.settlement { display: grid; gap: 20px; }
.settlement h3, .settlement h4, .settlement p { margin: 0; }
.settlement h3 { font-size: 17px; } .settlement h4 { font-size: 14px; overflow-wrap: anywhere; }
.settlement__identity { display: flex; justify-content: space-between; gap: 16px; align-items: start; flex-wrap: wrap; }
.settlement__identity > div { flex: 1; min-width: 220px; }
.settlement__identity p { color: var(--app-text-muted); font-size: 12px; margin-top: 4px; }
.settlement__meta, .settlement__metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 20px; margin: 0; }
.settlement dt { font-size: 12px; color: var(--app-text-muted); margin-bottom: 5px; }
.settlement dd { margin: 0; font-size: 15px; font-weight: 600; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.settlement__metrics { padding: 16px; border-radius: 10px; background: var(--app-surface-elevated); }
.settlement__meta dd { font-size: 13px; }
.settlement__hint { font-size: 12px; line-height: 1.6; color: var(--app-text-muted); }
.settlement__heading { display: flex; align-items: center; gap: 8px; }
.settlement__heading span { padding: 2px 8px; border-radius: 20px; background: var(--app-accent-soft); color: var(--app-accent); }
.settlement__shop { display: grid; gap: 14px; border: 1px solid var(--app-border); padding: 16px; border-radius: 12px; }
.settlement__form { border-top: 1px solid var(--app-border); padding-top: 16px; }
.settlement__form :deep(.n-input-number) { width: 100%; }
.settlement__actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.settlement__comment { white-space: pre-wrap; font-size: 13px; }
@media (max-width: 480px) { .settlement__metrics { grid-template-columns: 1fr; } }
</style>
