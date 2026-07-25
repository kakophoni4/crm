<script setup lang="ts">
import { NPopover } from 'naive-ui'
import { Smile } from 'lucide-vue-next'
import { ref } from 'vue'

import { CHAT_EMOJI_GROUPS } from '@/widgets/chat/emoji-data'

const emit = defineEmits<{
  pick: [emoji: string]
}>()

defineProps<{
  disabled?: boolean
}>()

const open = ref(false)

function onPick(emoji: string): void {
  emit('pick', emoji)
  open.value = false
}
</script>

<template>
  <NPopover v-model:show="open" trigger="click" placement="top-start" :width="320">
    <template #trigger>
      <button
        type="button"
        class="emoji-picker__trigger"
        :disabled="disabled"
        aria-label="Смайлы"
      >
        <Smile :size="18" />
      </button>
    </template>
    <div v-if="open" class="emoji-picker">
      <section v-for="group in CHAT_EMOJI_GROUPS" :key="group.label" class="emoji-picker__group">
        <p class="emoji-picker__label">{{ group.label }}</p>
        <div class="emoji-picker__grid">
          <button
            v-for="(emoji, idx) in group.emojis"
            :key="`${group.label}-${idx}-${emoji}`"
            type="button"
            class="emoji-picker__item"
            @click="onPick(emoji)"
          >
            {{ emoji }}
          </button>
        </div>
      </section>
    </div>
  </NPopover>
</template>

<style scoped>
.emoji-picker__trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: none;
  border-radius: var(--app-control-radius, 8px);
  background: transparent;
  color: var(--app-text-muted);
  cursor: pointer;
}

.emoji-picker__trigger:hover:not(:disabled) {
  background: var(--app-surface-elevated, #eee);
  color: var(--app-text);
}

.emoji-picker__trigger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.emoji-picker {
  max-height: 280px;
  overflow-y: auto;
  padding: 4px;
}

.emoji-picker__group + .emoji-picker__group {
  margin-top: 8px;
}

.emoji-picker__label {
  margin: 0 0 4px;
  font-size: 0.72rem;
  color: var(--app-text-muted);
}

.emoji-picker__grid {
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  gap: 2px;
}

.emoji-picker__item {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  aspect-ratio: 1;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  font-size: 1.25rem;
  line-height: 1;
  cursor: pointer;
}

.emoji-picker__item:hover {
  background: var(--app-surface-elevated, #eee);
}
</style>
