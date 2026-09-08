<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NInput, useMessage } from 'naive-ui'
import { AppError, http } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'
const props = defineProps<{ leadId: number; orderId: number; value?: string | null; disabled?: boolean }>()
const emit = defineEmits<{ saved: [value: string | null] }>()
const auth = useAuthStore()
const message = useMessage()
const draft = ref(props.value || '')
const saving = ref(false)
const editable = computed(() => !props.disabled && auth.user?.permissions.includes('contacts.update'))
watch(() => [props.orderId, props.value], () => { draft.value = props.value || '' })
async function save() {
  saving.value = true
  const orderId = props.orderId
  try {
    const { data } = await http.patch<{ buyer_okved: string | null }>(`/leads/${props.leadId}/opt-orders/${orderId}/okved`, { buyer_okved: draft.value.trim() || null })
    if (props.orderId === orderId) emit('saved', data.buyer_okved)
    message.success('ОКВЭД сохранён')
  } catch (err) { message.error(err instanceof AppError ? err.message : 'Не удалось сохранить ОКВЭД') }
  finally { saving.value = false }
}
</script>
<template>
  <div class="order-okved">
    <template v-if="editable">
      <NInput v-model:value="draft" :input-props="{ 'aria-label': 'ОКВЭД покупателя' }" placeholder="ОКВЭД" :maxlength="200" :disabled="saving" clearable @keydown.enter.prevent="save" />
      <NButton size="small" :loading="saving" :disabled="(draft.trim() || null) === (value || null)" @click="save">Сохранить</NButton>
    </template>
    <span v-else>{{ value || '—' }}</span>
  </div>
</template>
<style scoped>
.order-okved { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.order-okved :deep(.n-input) { width: 180px; }
</style>
