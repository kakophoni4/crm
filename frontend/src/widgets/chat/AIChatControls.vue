<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { NButton, NCheckbox, NPopover, NTag } from 'naive-ui'
import { http } from '@/shared/api/http'
const modeLabels: Record<string, string> = {
  OFF: 'ИИ выключен',
  ASSISTANT: 'Отвечает ИИ',
  MANAGER: 'Работает менеджер',
}
const props = defineProps<{ chatId: number }>()
type AIState = {
  mode: string
  manager?: string
  global_enabled: boolean
  data: {
    fallback_enabled?: boolean
    first_unanswered_at?: string
    fallback_done?: boolean
    error?: { message: string }
  }
}
const state = ref<AIState | null>(null),
  busy = ref(false),
  error = ref('')
let revision = 0
async function load() {
  const id = props.chatId
  const requestedRevision = revision
  try {
    const r = await http.get(`/ai/chats/${id}`)
    if (id === props.chatId && requestedRevision === revision) state.value = r.data
  } catch {
    if (id === props.chatId && requestedRevision === revision) state.value = null
  }
}
async function set(mode: string, fallback = false) {
  if (busy.value) return
  const id = props.chatId,
    requestedRevision = ++revision
  busy.value = true
  error.value = ''
  try {
    const { data } = await http.put(`/ai/chats/${id}`, { mode, fallback_enabled: fallback })
    if (id === props.chatId && requestedRevision === revision) state.value = data
  } catch (e) {
    if (id === props.chatId && requestedRevision === revision)
      error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (requestedRevision === revision) busy.value = false
  }
}
watch(
  () => props.chatId,
  () => {
    ++revision
    busy.value = false
    error.value = ''
    state.value = null
    void load()
  },
  { immediate: true },
)
const timer = setInterval(() => {
  if (!busy.value) void load()
}, 5000)
onBeforeUnmount(() => {
  ++revision
  clearInterval(timer)
})
</script>
<template>
  <div v-if="state" class="ai-controls">
    <NTag>{{ modeLabels[state.mode] }}</NTag
    ><span v-if="state.manager">{{ state.manager }}</span
    ><span v-if="!state.global_enabled">Автоответы выключены на сервере</span
    ><NPopover trigger="click" placement="bottom-start" display-directive="show">
      <template #trigger><NButton size="tiny" quaternary>Управление ИИ</NButton></template>
      <div class="ai-controls__menu">
        <NButton
          v-if="state.mode !== 'ASSISTANT'"
          size="small"
          :disabled="busy || !state.global_enabled"
          @click="set('ASSISTANT')"
          >Включить ИИ</NButton
        ><NButton
          v-if="state.mode !== 'MANAGER'"
          size="small"
          :disabled="busy"
          @click="set('MANAGER', state.data.fallback_enabled)"
          >Передать менеджеру</NButton
        ><NButton v-if="state.mode !== 'OFF'" size="small" :disabled="busy" @click="set('OFF')"
          >Выключить ИИ</NButton
        ><NCheckbox
          v-if="state.mode === 'MANAGER'"
          :checked="state.data.fallback_enabled"
          :disabled="busy"
          @update:checked="(v) => set('MANAGER', v)"
          >Подстраховка через 15 минут</NCheckbox
        >
      </div></NPopover
    >
    <span v-if="state.mode === 'MANAGER' && state.data.fallback_enabled"
      >Подстраховка включена</span
    >
    <span v-if="state.data.first_unanswered_at && !state.data.fallback_done"
      >Ожидание с {{ new Date(state.data.first_unanswered_at).toLocaleTimeString() }}</span
    ><span v-if="error || state.data.error" class="error">{{
      error || state.data.error?.message
    }}</span>
  </div>
</template>
<style scoped>
.ai-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-surface);
  font-size: 12px;
  color: var(--app-text-muted);
}
.error {
  color: var(--app-danger);
}
.ai-controls__menu {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: min(250px, 80vw);
}
.ai-controls {
  flex-shrink: 0;
}
.ai-controls > span {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
