<script setup lang="ts">
import { ref, watch, onBeforeUnmount } from 'vue'
import { NButton, NCheckbox, NTag } from 'naive-ui'
import { http } from '@/shared/api/http'
const modeLabels: Record<string, string> = {
  OFF: 'ИИ выключен',
  ASSISTANT: 'Отвечает ИИ',
  MANAGER: 'Работает менеджер',
}
const props = defineProps<{ chatId: number }>()
type AIState={mode:string;manager?:string;global_enabled:boolean;data:{fallback_enabled?:boolean;first_unanswered_at?:string;fallback_done?:boolean;error?:{message:string}}}
const state = ref<AIState | null>(null),
  busy = ref(false),
  error = ref('')
async function load() {
  const id = props.chatId
  try {
    const r = await http.get(`/ai/chats/${id}`)
    if (id === props.chatId) state.value = r.data
  } catch {
    state.value = null
  }
}
async function set(mode: string, fallback = false) {
  busy.value = true
  error.value = ''
  try {
    state.value = (
      await http.put(`/ai/chats/${props.chatId}`, { mode, fallback_enabled: fallback })
    ).data
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
watch(
  () => props.chatId,
  () => {
    state.value = null
    void load()
  },
  { immediate: true },
)
const timer = setInterval(() => {
  if (!busy.value) void load()
}, 5000)
onBeforeUnmount(() => clearInterval(timer))
</script>
<template>
  <div v-if="state" class="ai-controls">
    <NTag>{{ modeLabels[state.mode] }}</NTag
    ><span v-if="state.manager">{{ state.manager }}</span
    ><span v-if="!state.global_enabled">Автоответы выключены на сервере</span
    ><NButton size="tiny" :disabled="busy || !state.global_enabled" @click="set('ASSISTANT')"
      >Включить ИИ</NButton
    ><NButton size="tiny" :disabled="busy" @click="set('MANAGER', state.data.fallback_enabled)"
      >Передать менеджеру</NButton
    ><NButton size="tiny" :disabled="busy" @click="set('OFF')">Выключить</NButton
    ><NCheckbox
      v-if="state.mode === 'MANAGER'"
      :checked="state.data.fallback_enabled"
      :disabled="busy"
      @update:checked="(v) => set('MANAGER', v)"
      >Подстраховка через 15 минут</NCheckbox
    ><span v-if="state.data.first_unanswered_at && !state.data.fallback_done"
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
</style>
