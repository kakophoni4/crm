<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NRadioGroup, NRadioButton, NEmpty, NPopover, NCheckbox, NInput } from 'naive-ui'
import type { OptPaymentRegisterItem as Order } from './opt-types'
import PaymentRegisterDetail from './PaymentRegisterDetail.vue'
const props = defineProps<{ items: Order[] }>()
const emit = defineEmits<{ open: [Order]; saved: [] }>()
const fmt = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 })
const money = (n: number) => fmt.format(n)
const unique = (values: (string | null | undefined)[]) => [...new Set(values.filter(Boolean))].join('\n') || '—'
const sum = (o: Order, key: 'beneficiary_amount' | 'beneficiary_paid_amount') => o.lines.reduce((n,l) => n + Number(l[key]), 0)
const known = (o: Order) => o.lines.length > 0 && o.lines.every(l => l.beneficiary_rate_percent != null)
const rates = (o: Order, key: 'our_rate_percent' | 'beneficiary_rate_percent') => unique(o.lines.map(l => l[key] == null ? 'Не задана' : `${fmt.format(Number(l[key]))}%`))
type Column = { key: string; label: string; numeric?: boolean; value: (o: Order) => string; total?: (o: Order) => number | null }
const columns: Column[] = [
 {key:'client',label:'Клиент',value:o=>o.client_name || 'Без имени'},
 {key:'manager',label:'Менеджер',value:o=>o.manager_name || '—'},
 {key:'okved',label:'ОКВЭД',value:o=>o.client_okved || '—'},
 {key:'buyer',label:'Лавка клиента',value:o=>o.client_shop_name || o.client_inn},
 {key:'supplier',label:'Наша лавка',value:o=>unique(o.lines.map(l=>l.supplier_name || l.supplier_inn))},
 {key:'inn',label:'ИНН покупателя',value:o=>o.client_inn},
 {key:'period',label:'Период',value:o=>o.period_code || '—'},
 {key:'category',label:'Категория',value:o=>unique(o.lines.map(l=>l.category_code))},
 {key:'volume',label:'Объём, ₽',numeric:true,value:o=>money(Number(o.volume)),total:o=>Number(o.volume)},
 {key:'rate',label:'Наша цена, %',numeric:true,value:o=>rates(o,'our_rate_percent')},
 {key:'due',label:'К оплате, ₽',numeric:true,value:o=>money(Number(o.due_amount)),total:o=>Number(o.due_amount)},
 {key:'paid',label:'Оплачено, ₽',numeric:true,value:o=>money(Number(o.paid_amount)),total:o=>Number(o.paid_amount)},
 {key:'debt',label:'Долг, ₽',numeric:true,value:o=>money(Number(o.due_amount)-Number(o.paid_amount)),total:o=>Number(o.due_amount)-Number(o.paid_amount)},
 {key:'comment',label:'Комментарий',value:o=>unique(o.lines.map(l=>l.comment))},
 {key:'benRate',label:'Цена бена, %',numeric:true,value:o=>rates(o,'beneficiary_rate_percent')},
 {key:'ben',label:'Цена бена, ₽',numeric:true,value:o=>known(o)?money(sum(o,'beneficiary_amount')):'Не заполнено',total:o=>known(o)?sum(o,'beneficiary_amount'):null},
 {key:'margin',label:'Маржа после начисления, ₽',numeric:true,value:o=>known(o)?money(Number(o.paid_amount)-sum(o,'beneficiary_amount')):'Не определена',total:o=>known(o)?Number(o.paid_amount)-sum(o,'beneficiary_amount'):null},
 {key:'plan',label:'Плановая маржа, ₽',numeric:true,value:o=>known(o)?money(Number(o.due_amount)-sum(o,'beneficiary_amount')):'Не определена',total:o=>known(o)?Number(o.due_amount)-sum(o,'beneficiary_amount'):null},
 {key:'returned',label:'Вернули бену, ₽',numeric:true,value:o=>money(sum(o,'beneficiary_paid_amount')),total:o=>sum(o,'beneficiary_paid_amount')},
]
const presets: Record<string,string[]> = {
 sales:['client','buyer','supplier','period','volume','rate','due','paid','debt'],
 money:['client','manager','buyer','due','paid','debt','comment'],
 beneficiary:['client','supplier','volume','benRate','ben','margin','plan','returned'],
}
const mode=ref('sales'), selected=ref([...presets.sales])
try { const saved=JSON.parse(localStorage.getItem('sales-register-columns-v2') || 'null'); if(Array.isArray(saved) && saved.length) { selected.value=saved.filter(k=>columns.some(c=>c.key===k)); mode.value='custom' } } catch { /* Use defaults if storage is unavailable. */ }
watch(selected,v=>{try{localStorage.setItem('sales-register-columns-v2',JSON.stringify(v))}catch{}},{deep:true})
const visible=computed(()=>columns.filter(c=>selected.value.includes(c.key)))
function preset(value:string) {mode.value=value; selected.value=[...presets[value]]}
function toggle(key:string,checked:boolean) {mode.value='custom';selected.value=checked?[...selected.value,key]:selected.value.filter(k=>k!==key)}
const query=ref(''), expanded=ref<number|null>(null), sort=ref(''), descending=ref(false)
const rows=computed(()=>{
 const q=query.value.trim().toLocaleLowerCase('ru')
 const data=props.items.filter(o=>!q || [o.order_no,o.lead_id,...columns.map(c=>c.value(o))].join(' ').toLocaleLowerCase('ru').includes(q))
 const c=columns.find(c=>c.key===sort.value)
 return c ? data.slice().sort((a,b)=>{const av=c.total?.(a),bv=c.total?.(b);return (av!=null&&bv!=null?av-bv:c.value(a).localeCompare(c.value(b),'ru',{numeric:true}))*(descending.value?-1:1)}) : data
})
function sortBy(key:string) {descending.value=sort.value===key?!descending.value:false;sort.value=key}
function total(c:Column) {if(!c.total)return '';const values=rows.value.map(c.total);return values.some(v=>v==null)?'Не определено':money(values.reduce<number>((n,v)=>n+Number(v),0))}
</script>
<template>
 <section class="sales-register">
  <div class="register-toolbar">
   <NRadioGroup :value="mode" size="small" aria-label="Колонки таблицы" @update:value="preset">
    <NRadioButton value="sales">Продажи</NRadioButton><NRadioButton value="money">Расчёты</NRadioButton><NRadioButton value="beneficiary">Бенефициар</NRadioButton>
   </NRadioGroup>
   <NPopover trigger="click" placement="bottom-end"><template #trigger><NButton size="small">Колонки · {{ visible.length }}</NButton></template>
    <div class="column-picker"><NCheckbox v-for="c in columns" :key="c.key" :checked="selected.includes(c.key)" :disabled="selected.length===1 && selected.includes(c.key)" @update:checked="v=>toggle(c.key,v)">{{ c.label }}</NCheckbox></div>
   </NPopover>
   <NInput v-model:value="query" clearable size="small" placeholder="Найти на этой странице" aria-label="Найти на этой странице" class="register-search" />
  </div>
  <p class="register-hint">Одна строка — одна заявка. Сортировка, поиск и нижний итог — по текущей странице. Отрицательный долг — переплата.</p>
  <NEmpty v-if="!rows.length" description="Заявок не найдено" />
  <div v-else class="register-grid" tabindex="0" aria-label="Таблица продаж">
   <table :class="{'table-wide':visible.length>11}">
    <caption class="sr-only">Реестр продаж. Все суммы в рублях.</caption>
    <thead><tr><th class="order-col">№ заявки</th><th v-for="c in visible" :key="c.key" :class="{numeric:c.numeric}" :aria-sort="sort===c.key?(descending?'descending':'ascending'):'none'"><button @click="sortBy(c.key)">{{ c.label }}<span v-if="sort===c.key"> {{ descending?'↓':'↑' }}</span></button></th><th class="actions-col">Детали</th></tr></thead>
    <tbody><template v-for="o in rows" :key="o.id">
     <tr :class="{'row-selected':expanded===o.id}"><td class="order-col"><button class="order-link" @click="emit('open',o)">№{{ o.order_no }}</button><small>Сделка {{ o.lead_id }}</small></td>
      <td v-for="c in visible" :key="c.key" :class="{numeric:c.numeric, debt:c.key==='debt' && Number(o.due_amount)>Number(o.paid_amount)}"><details v-if="c.value(o).split('\n').length > 2" class="cell-details"><summary>{{ c.value(o).split('\n').slice(0,2).join('\n') }}<small>Ещё {{ c.value(o).split('\n').length-2 }} · раскрыть</small></summary>{{ c.value(o).split('\n').slice(2).join('\n') }}</details><span v-else>{{ c.value(o) }}</span></td>
      <td><NButton size="tiny" quaternary :aria-expanded="expanded===o.id" :aria-label="`Детали заявки ${o.order_no}, сделка ${o.lead_id}`" @click="expanded=expanded===o.id?null:o.id">{{ expanded===o.id?'Скрыть':'Открыть' }}</NButton></td>
     </tr>
     <tr v-if="expanded===o.id" class="detail-row"><td :colspan="visible.length+2"><PaymentRegisterDetail :order="o" @saved="emit('saved')" /></td></tr>
    </template></tbody>
    <tfoot><tr><th>Итого<small>{{ rows.length }} заявок</small></th><td v-for="c in visible" :key="c.key" :class="{numeric:c.numeric}">{{ total(c) }}</td><td /></tr></tfoot>
   </table>
  </div>
 </section>
</template>
<style scoped>
.sales-register{min-width:0;max-width:100%;color:var(--app-text)}
.register-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.register-search{max-width:280px;margin-left:auto}.register-hint{font-size:12px;color:var(--app-text-muted);margin:8px 0}
.column-picker{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;max-height:65vh;overflow:auto}
.register-grid{max-height:65vh;overflow:auto;border:1px solid var(--app-border);border-radius:6px}
table{width:100%;table-layout:fixed;border-spacing:0;font-size:12px;line-height:1.45}
th,td{padding:8px 7px;border-right:1px solid var(--app-border);border-bottom:1px solid var(--app-border);vertical-align:top;text-align:left;overflow-wrap:anywhere;white-space:pre-line}
thead th{position:sticky;top:0;background:var(--app-surface);z-index:2;vertical-align:middle}
th button{border:0;background:none;color:inherit;font:inherit;font-weight:600;cursor:pointer;text-align:inherit;padding:0;width:100%}
.order-col{width:78px}.actions-col{width:66px}.order-link{border:0;background:none;color:var(--app-accent);font:inherit;font-weight:600;padding:0;cursor:pointer}
small{display:block;color:var(--app-text-muted);font-size:10px;margin-top:3px}
.numeric{text-align:right;font-variant-numeric:tabular-nums}.debt{color:var(--app-danger,#d03050)}
tbody tr:nth-child(even){background:color-mix(in srgb,var(--app-text) 3%,transparent)}
tbody tr:hover,.row-selected{background:color-mix(in srgb,var(--app-accent) 8%,transparent)}
tfoot{background:var(--app-surface);font-weight:600}.detail-row td{padding:16px;background:var(--app-surface)}
.cell-details summary{cursor:pointer;list-style:none}.cell-details summary small{color:var(--app-accent)}
.table-wide{min-width:1800px}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
@media(max-width:1050px){table{min-width:1050px}.register-search{margin-left:0}}
</style>
