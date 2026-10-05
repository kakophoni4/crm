<script setup lang="ts">
import { ref, watch } from 'vue'
import { NButton, NSelect, useMessage } from 'naive-ui'
import { http } from '@/shared/api/http'
import { DEVICE_LIMIT_OPTIONS } from './device-limit'

const props = defineProps<{ subscriptionId: string; deviceLimit: number }>()
const emit = defineEmits<{ saved: [] }>()
const message = useMessage()
const selected = ref(props.deviceLimit)
const saving = ref(false)
watch(() => [props.subscriptionId, props.deviceLimit], () => { selected.value = props.deviceLimit })
async function save() {
  if (saving.value || selected.value === props.deviceLimit) return
  const identity = props.subscriptionId
  saving.value = true
  try {
    await http.post(`/vpn/subscriptions/${identity}/action`, { action: 'set_device_limit', device_limit: selected.value })
    if (props.subscriptionId !== identity) return
    message.success('Лимит подключений сохранён')
    emit('saved')
  } catch (error) { message.error(error instanceof Error ? error.message : 'Не удалось изменить лимит') }
  finally { saving.value = false }
}
</script>
<template>
  <div class="device-limit">
    <label :for="`vpn-device-limit-${subscriptionId}`">Лимит подключений</label>
    <div class="device-limit__controls">
      <NSelect :input-props="{ id: `vpn-device-limit-${subscriptionId}`, 'aria-label': 'Лимит подключений' }" v-model:value="selected" :options="DEVICE_LIMIT_OPTIONS" :disabled="saving" size="small" />
      <NButton size="small" secondary :loading="saving" :disabled="saving || selected === deviceLimit" @click="save">Сохранить</NButton>
    </div>
  </div>
</template>
<style scoped>
.device-limit { display: grid; gap: 6px; margin: 12px 0; }
.device-limit label { font-size: 12px; font-weight: 600; }
.device-limit__controls { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; align-items: center; }
.device-limit small { font-size: 11px; color: var(--app-text-muted); }
</style>
