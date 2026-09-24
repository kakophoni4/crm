<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { NButton, NInput, NModal, NTag } from 'naive-ui'
import { http } from '@/shared/api/http'

const props = defineProps<{ chatId: number; contactName: string }>()
type State = { status: 'none' | 'pending' | 'blocked' | 'failed' | 'unsupported'; reason?: string; operator?: string; requested_at?: string }
const state = ref<State | null>(null)
const open = ref(false)
const reason = ref('')
const busy = ref(false)
const error = ref('')
const controller = new AbortController()
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
const path = `/chats/${props.chatId}/telegram-block`
function poll() {
  if (timer) clearTimeout(timer)
  if (!disposed && state.value?.status === 'pending') timer = setTimeout(load, 5000)
}
async function load() {
  try {
    const { data } = await http.get<State>(path, { signal: controller.signal })
    if (disposed) return
    state.value = data
    error.value = ''
  } catch {
    if (!disposed) error.value = 'Не удалось проверить блокировку'
  } finally { poll() }
}
async function block() {
  busy.value = true
  error.value = ''
  try {
    const { data } = await http.post<State>(path, { reason: reason.value.trim() }, { signal: controller.signal })
    if (disposed) return
    state.value = data
    open.value = false
    poll()
  } catch {
    await load()
    if (!disposed && !['blocked', 'pending'].includes(state.value?.status ?? '')) error.value = 'Запрос не подтверждён. Проверьте статус перед повтором.'
  } finally { busy.value = false }
}
onMounted(load)
onUnmounted(() => { disposed = true; controller.abort(); if (timer) clearTimeout(timer) })
</script>

<template>
  <div v-if="state?.status !== 'unsupported'" class="block-contact">
    <NTag v-if="state?.status === 'blocked'" type="error" size="small" :bordered="false">
      Заблокирован во всех ботах
    </NTag>
    <NTag v-else-if="state?.status === 'pending'" type="warning" size="small" :bordered="false">
      Блокировка запрошена
    </NTag>
    <NButton v-else-if="state" size="small" quaternary type="error" @click="open = true">
      {{ state.status === 'failed' ? 'Повторить блокировку' : 'Заблокировать' }}
    </NButton>
    <small v-if="state?.status === 'failed'">Мост не подтвердил блокировку</small>
    <small v-if="state?.status === 'blocked' && state.operator">{{ state.operator }}<template v-if="state.reason"> · {{ state.reason }}</template></small>
    <NButton v-if="error" size="tiny" quaternary @click="load">{{ error }} · Проверить</NButton>
    <NModal v-model:show="open" preset="card" title="Заблокировать пользователя?" :mask-closable="!busy" :closable="!busy" style="width: 440px; max-width: 94vw">
      <p><strong>{{ contactName }}</strong> будет заблокирован во всех Telegram-ботах: его сообщения перестанут поступать в CRM, рассылки будут его пропускать.</p>
      <p>Разблокировки в CRM нет.</p>
      <NInput v-model:value="reason" type="textarea" placeholder="Причина (необязательно)" :maxlength="500" :autosize="{ minRows: 2, maxRows: 4 }" :disabled="busy" />
      <p v-if="error" role="alert">{{ error }}</p>
      <template #footer>
        <div class="block-contact__actions">
          <NButton :disabled="busy" @click="open = false">Отмена</NButton>
          <NButton type="error" :loading="busy" :disabled="busy || state?.status === 'blocked' || state?.status === 'pending'" @click="block">Заблокировать во всех ботах</NButton>
        </div>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.block-contact { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; max-width: 300px; }
.block-contact small { font-size: 11px; color: var(--app-text-muted); overflow-wrap: anywhere; }
.block-contact__actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 8px; }
</style>
