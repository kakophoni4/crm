<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NRadioGroup, NRadioButton, NEmpty } from 'naive-ui'
import type { OptPaymentRegisterItem } from './opt-types'
import PaymentRegisterDetail from './PaymentRegisterDetail.vue'
defineProps<{ items: OptPaymentRegisterItem[] }>()
const emit = defineEmits<{ open: [OptPaymentRegisterItem]; saved: [] }>()
const mode = ref('sales')
const expanded = ref<number | null>(null)
const money = (v: number) => new Intl.NumberFormat('ru-RU', {maximumFractionDigits:2}).format(Number(v)) + ' ₽'
</script>
<template>
  <div class="sales-register">
    <NRadioGroup v-model:value="mode" size="small" aria-label="Колонки таблицы">
      <NRadioButton value="sales">Продажи</NRadioButton><NRadioButton value="money">Расчёты</NRadioButton><NRadioButton value="beneficiary">Бенефициар</NRadioButton>
    </NRadioGroup>
    <NEmpty v-if="!items.length" description="По этим фильтрам заявок нет" />
    <table v-else>
      <caption class="sr-only">Таблица продаж. Оплаты и остатки показаны на уровне заявки.</caption>
      <thead><tr><th>Заявка / клиент</th><th>{{ mode === 'sales' ? 'Лавки / период' : 'Расчёт' }}</th><th>Суммы</th><th>Действия</th></tr></thead>
      <tbody>
        <template v-for="row in items" :key="row.id">
          <tr>
            <td><strong>№{{ row.order_no }}</strong><br>{{ row.client_name || 'Без имени' }}<br><small>{{ row.manager_name }} · {{ row.client_inn }}</small><br><small v-if="row.client_okved">ОКВЭД: {{ row.client_okved }}</small></td>
            <td v-if="mode === 'sales'">{{ row.client_shop_name }}<br><span v-for="inn in [...new Set(row.lines.map(l => l.supplier_inn))]" :key="inn" class="supplier">{{ row.lines.find(l => l.supplier_inn === inn)?.supplier_name || inn }}</span><small>Отчётный период: {{ row.period_code || '—' }}</small></td>
            <td v-else-if="mode === 'money'">К оплате: {{ money(row.due_amount) }}<br>Оплачено: {{ money(row.paid_amount) }}<br>{{ Number(row.paid_amount) > Number(row.due_amount) ? 'Переплата' : 'Остаток' }}: {{ money(Math.abs(Number(row.due_amount) - Number(row.paid_amount))) }}</td>
            <td v-else>Начислено: {{ row.lines.some(l => l.beneficiary_rate_percent == null) ? 'Не заполнено' : money(row.lines.reduce((n,l) => n + Number(l.beneficiary_amount), 0)) }}<br>Выплачено: {{ money(row.lines.reduce((n,l) => n + Number(l.beneficiary_paid_amount), 0)) }}<br><small v-if="row.lines.some(l => l.beneficiary_rate_percent == null)">Не все условия заполнены</small></td>
            <td v-if="mode === 'sales'">Объём: {{ money(row.volume) }}<br>К оплате: {{ money(row.due_amount) }}<br>Оплачено: {{ money(row.paid_amount) }}</td>
            <td v-else-if="mode === 'money'">{{ row.is_paid ? 'Оплачено' : Number(row.paid_amount) > 0 ? 'Частичная оплата' : 'Не оплачено' }}</td>
            <td v-else>Плановая маржа: {{ row.lines.some(l => l.beneficiary_rate_percent == null) ? 'Не определена' : money(Number(row.due_amount) - row.lines.reduce((n,l) => n + Number(l.beneficiary_amount), 0)) }}<br>Денежный остаток: {{ money(Number(row.paid_amount) - row.lines.reduce((n,l) => n + Number(l.beneficiary_paid_amount), 0)) }}</td>
            <td><NButton size="small" @click="emit('open',row)">Заявка</NButton><NButton size="small" quaternary @click="expanded = expanded === row.id ? null : row.id">{{ expanded === row.id ? 'Свернуть' : 'Подробнее' }}</NButton></td>
          </tr>
          <tr v-if="expanded === row.id"><td colspan="4"><PaymentRegisterDetail :order="row" @saved="emit('saved')" /></td></tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
<style scoped>
.sales-register { min-width: 0; overflow-y: auto; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; margin-top: 12px; }
th, td { padding: 12px; text-align: left; vertical-align: top; overflow-wrap: anywhere; white-space: normal; border-bottom: 1px solid var(--app-border); color: var(--app-text); }
th { background: var(--app-surface); position: sticky; top: 0; z-index: 1; }
th:last-child { width: 105px; }
small { color: var(--app-text-muted); }
.supplier { display: block; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
@media(max-width: 700px) { thead { display: none; } tr { display: grid; grid-template-columns: 1fr; border-bottom: 2px solid var(--app-border); } td { display: block; border: 0; padding: 6px 10px; } }
</style>
