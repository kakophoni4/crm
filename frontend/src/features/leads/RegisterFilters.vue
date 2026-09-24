<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NSelect, NInput, NInputNumber, NPopover, NCheckbox } from 'naive-ui'
import { registerFields, type RegisterQuery, type RegisterFilters } from './register-query'
const props=defineProps<{ modelValue: RegisterQuery; allowManager: boolean }>()
const emit=defineEmits<{ 'update:modelValue':[RegisterQuery] }>()
const fields=computed(()=>registerFields.filter(f=>f.value!=='manager' || props.allowManager))
const chosen=ref<string[]>([])
const draft=ref<RegisterFilters>({})
const error=ref('')
watch(()=>props.modelValue.filters,v=>{draft.value=JSON.parse(JSON.stringify(v)); chosen.value=Object.keys(v)}, {immediate:true})
function choose(key:string,on:boolean) {
  chosen.value=on?[...chosen.value,key]:chosen.value.filter(k=>k!==key)
  if(!on) {
    delete draft.value[key]
    if(key in props.modelValue.filters) {
      const filters={...props.modelValue.filters};delete filters[key]
      emit('update:modelValue',{...props.modelValue,filters})
    }
  }
}
function textValue(key:string) { const v=draft.value[key];return typeof v==='string'?v:'' }
function bound(key:string,which:'min'|'max') { const v=draft.value[key];return typeof v==='object'?v[which]??null:null }
function setBound(key:string,which:'min'|'max',value:number|null) {const v=draft.value[key];draft.value[key]={...(typeof v==='object'?v:{}),[which]:value}}
function apply() {
  for(const v of Object.values(draft.value)) if(typeof v==='object' && v.min!=null && v.max!=null && v.min>v.max) {error.value='Минимум не может быть больше максимума';return}
  error.value='';emit('update:modelValue',{...props.modelValue,filters:JSON.parse(JSON.stringify(draft.value))})
}
function reset(){ chosen.value=[];draft.value={};error.value='';emit('update:modelValue',{filters:{},sort:null,descending:true}) }
</script>
<template>
 <div class="register-filters">
  <div class="register-filters__bar">
   <NPopover trigger="click" placement="bottom-start"><template #trigger><NButton size="small">Фильтры колонок · {{ chosen.length }}</NButton></template>
    <div class="register-filters__picker"><NCheckbox v-for="f in fields" :key="f.value" :checked="chosen.includes(f.value)" @update:checked="v=>choose(f.value,v)">{{ f.label }}</NCheckbox></div>
   </NPopover>
   <NSelect size="small" :value="modelValue.sort" :options="fields" clearable placeholder="Сортировать все заявки" aria-label="Сортировать все заявки" class="register-filters__sort" @update:value="v=>emit('update:modelValue',{...modelValue,sort:v})" />
   <NButton v-if="modelValue.sort" size="small" @click="emit('update:modelValue',{...modelValue,descending:!modelValue.descending})">{{ modelValue.descending?'По убыванию ↓':'По возрастанию ↑' }}</NButton>
   <NButton v-if="chosen.length || modelValue.sort" size="small" quaternary @click="reset">Сбросить фильтры таблицы</NButton>
   <span class="register-filters__hint">По всем доступным заявкам</span>
  </div>
  <form v-if="chosen.length" class="register-filters__fields" @submit.prevent="apply">
   <div v-for="f in fields.filter(f=>chosen.includes(f.value))" :key="f.value" class="register-filters__field">
    <label>{{ f.label }}</label>
    <div v-if="f.numeric" class="register-filters__range">
     <NInputNumber :value="bound(f.value,'min')" :input-props="{'aria-label':f.label+' от'}" size="small" placeholder="От" :show-button="false" @update:value="v=>setBound(f.value,'min',v)" />
     <NInputNumber :value="bound(f.value,'max')" :input-props="{'aria-label':f.label+' до'}" size="small" placeholder="До" :show-button="false" @update:value="v=>setBound(f.value,'max',v)" />
    </div>
    <NInput v-else :value="textValue(f.value)" :input-props="{'aria-label':f.label+' содержит'}" size="small" placeholder="Содержит…" clearable :maxlength="160" @update:value="v=>draft[f.value]=v" />
   </div>
   <NButton size="small" type="primary" attr-type="submit">Применить</NButton>
   <span v-if="error" role="alert">{{ error }}</span>
  </form>
 </div>
</template>
<style scoped>
.register-filters{display:flex;flex-direction:column;gap:8px;padding:8px 10px;border:1px solid var(--app-border);border-radius:8px;flex-shrink:0}
.register-filters__bar,.register-filters__fields{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.register-filters__fields{align-items:flex-end}
.register-filters__sort{width:230px}.register-filters__hint{font-size:11px;color:var(--app-text-muted);margin-left:auto}
.register-filters__field{width:220px;max-width:100%;display:flex;flex-direction:column;gap:4px}.register-filters__field label{font-size:12px;color:var(--app-text-muted)}
.register-filters__range{display:flex;gap:5px}.register-filters__range>*{min-width:0;flex:1}.register-filters__picker{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;max-width:90vw}
</style>
