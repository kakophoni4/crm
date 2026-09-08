<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NEmpty, NPagination, NTag } from 'naive-ui'
import type { LawyerShop } from './types'
const props = defineProps<{ shops: LawyerShop[] }>()
const page = ref(1)
const pageSize = 20
const visible = computed(() => props.shops.slice((page.value - 1) * pageSize, page.value * pageSize))
watch(() => props.shops, () => { page.value = 1 })
function facts(shop: LawyerShop): Array<[string, string | null]> {
  return [
    ['Директор', shop.director_name], ['Статус компании', shop.company_status],
    ['Дата приёма', shop.received_at ?? null], ['ФНС', shop.fns], ['Дата регистрации', shop.registered_at], ['Счета', shop.accounts_status],
    ['Банки', shop.banks], ['ЭЦП', shop.ecsp_status], ['ЭЦП действует до', shop.ecsp_until],
    ['СБИС', shop.sbis], ['ЭДО действует до', shop.edo_until], ['Идентификатор ЭДО', shop.edo_id],
    ['Дата покупки', shop.purchased_at], ['Недостоверность', shop.unreliable],
    ['Работа по тикетам', shop.treatment_status], ['Дата слёта', shop.failed_at], ['Причина слёта', shop.failure_reason],
  ]
}
</script>
<template>
  <NEmpty v-if="!shops.length" description="По этим фильтрам нет назначенных вам лавок" />
  <div v-else class="assigned-shops">

    <article v-for="shop in visible" :key="shop.id" class="assigned-shops__card">
      <header><div><h3>{{ shop.name }}</h3><p>ИНН {{ shop.inn }}</p></div><NTag size="small" :bordered="false">Только просмотр</NTag></header>
      <dl><div v-for="[label, value] in facts(shop)" :key="label"><dt>{{ label }}</dt><dd>{{ value || 'Не заполнено' }}</dd></div></dl>
      <p v-if="shop.comment" class="assigned-shops__comment">{{ shop.comment }}</p>
    </article>
    <NPagination v-if="shops.length > pageSize" v-model:page="page" :page-size="pageSize" :item-count="shops.length" />
  </div>
</template>
<style scoped>
.assigned-shops { display: grid; gap: 16px; }
.assigned-shops__card { padding: 20px; border: 1px solid var(--app-border); border-radius: 12px; }
.assigned-shops__card header { display: flex; gap: 12px; justify-content: space-between; align-items: start; flex-wrap: wrap; }
.assigned-shops__card h3 { margin: 0; font-size: 15px; overflow-wrap: anywhere; }
.assigned-shops__card header p, .assigned-shops__hint { color: var(--app-text-muted); font-size: 12px; }
.assigned-shops dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 16px; margin: 16px 0 0; }
.assigned-shops dt { font-size: 12px; color: var(--app-text-muted); }
.assigned-shops dd { margin: 4px 0 0; overflow-wrap: anywhere; }
.assigned-shops__comment { white-space: pre-wrap; border-top: 1px solid var(--app-border); padding-top: 12px; }
</style>
