<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { http } from '@/shared/api/http'
const props=defineProps<{ path:string; initial?:string }>()
const result=ref<string|null>(props.initial ?? null), busy=ref(false), error=ref(''), open=ref(false)
let timer:ReturnType<typeof setTimeout>|undefined
let controller:AbortController|undefined
let started=0
function stop(){if(timer)clearTimeout(timer);controller?.abort();busy.value=false}
watch(()=>props.path,()=>{stop();result.value=props.initial ?? null;open.value=false;error.value=''})
async function request(start:boolean){
 const signal=controller!.signal
 try{
  const url=`${props.path}/transcription`
  const {data}=start?await http.post(url,null,{signal}):await http.get(url,{signal})
  if(signal.aborted)return
  if(data.status==='ready'){result.value=data.text;busy.value=false;open.value=true;return}
  if(data.status==='processing' && Date.now()-started<15*60*1000){timer=setTimeout(()=>void request(false),3000);return}
  error.value=data.error || 'Распознавание занимает больше времени. Нажмите «В текст» позже';busy.value=false
 }catch{if(!signal.aborted){error.value='Не удалось получить расшифровку. Повторите попытку';busy.value=false}}
}
function toggle(){
 if(result.value!==null){open.value=!open.value;return}
 if(busy.value)return
 controller=new AbortController();started=Date.now();busy.value=true;error.value='';void request(true)
}
onBeforeUnmount(stop)
</script>
<template>
 <div class="voice-transcript">
  <button :disabled="busy" @click="toggle">{{ busy?'Распознаём на сервере…':result!==null?(open?'Скрыть текст':'Показать текст'):'В текст' }}</button>
  <p v-if="error" role="alert">{{ error }}</p>
  <div v-if="open && result!==null" class="voice-transcript__text">{{ result || 'Речь не обнаружена' }}<small>Автоматическая расшифровка · возможны ошибки</small></div>
 </div>
</template>
<style scoped>
.voice-transcript{max-width:320px;font-size:12px}.voice-transcript button{border:0;border-radius:8px;background:color-mix(in srgb,var(--app-accent) 10%,transparent);color:var(--app-accent);padding:4px 10px;font:inherit;cursor:pointer}.voice-transcript button:disabled{cursor:wait}.voice-transcript__text{white-space:pre-wrap;overflow-wrap:anywhere;margin-top:8px;line-height:1.6;color:var(--app-text);user-select:text}.voice-transcript small{display:block;font-size:10px;color:var(--app-text-muted);margin-top:6px}.voice-transcript p{color:var(--app-danger);overflow-wrap:anywhere}
</style>
