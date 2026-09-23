<script setup lang="ts">
import { ref, computed } from 'vue'
import { NButton, NSelect, NSpace, useMessage } from 'naive-ui'
import { listStatuses } from '@/features/admin/api'
import { useAuthStore } from '@/shared/store/auth'
import { http, AppError } from '@/shared/api/http'
const props = defineProps<{ leadId: number }>()
const emit = defineEmits<{ reopened: [] }>()
const auth = useAuthStore()
const allowed = computed(() => auth.user?.permissions.includes('contacts.update'))
const open = ref(false)
const busy = ref(false)
const status = ref<number | null>(null)
const options = ref<{label:string;value:number}[]>([])
const message = useMessage()
async function begin() {
  try {
    const rows = await listStatuses({kind:'lead_pipeline'})
    options.value = rows.filter(r => !['won','lost'].includes(r.code)).map(r => ({label:r.label,value:r.id}))
    status.value = null
    open.value = true
  } catch { message.error('Не удалось загрузить статусы') }
}
async function save() {
  if (status.value == null) return
  busy.value = true
  try { await http.post(`/leads/${props.leadId}/reopen`, {status_id:status.value}); open.value = false; emit('reopened'); message.success('Сделка возвращена в работу') }
  catch(e) { message.error(e instanceof AppError ? e.message : 'Не удалось открыть сделку') }
  finally { busy.value = false }
}
</script>
<template><div v-if="allowed"><NButton v-if="!open" @click="begin">Вернуть в работу</NButton><NSpace v-else vertical><NSelect v-model:value="status" :options="options" placeholder="Выберите рабочий статус" /><NSpace><NButton :disabled="status == null" :loading="busy" type="primary" @click="save">Вернуть в работу</NButton><NButton :disabled="busy" @click="open = false">Отмена</NButton></NSpace></NSpace></div></template>
