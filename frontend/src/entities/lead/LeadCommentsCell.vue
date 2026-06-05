<script setup lang="ts">
import { NButton } from 'naive-ui'
import { format } from 'date-fns'
import { computed, ref } from 'vue'

import type { LeadCommentItem } from '@/features/leads/types'

const props = defineProps<{
  comments: LeadCommentItem[]
}>()

const expanded = ref(false)

const sorted = computed(() =>
  [...props.comments].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  ),
)

const latest = computed(() => sorted.value[sorted.value.length - 1] ?? null)
const hasMultiple = computed(() => sorted.value.length > 1)
const hiddenCount = computed(() => Math.max(0, sorted.value.length - 1))

function formatWhen(iso: string): string {
  try {
    return format(new Date(iso), 'dd.MM.yyyy HH:mm')
  } catch {
    return iso
  }
}
</script>

<template>
  <div v-if="latest" class="lead-comments-cell">
    <p class="lead-comments-cell__text">{{ latest.body }}</p>
    <span class="lead-comments-cell__meta">{{ formatWhen(latest.created_at) }}</span>
    <NButton
      v-if="hasMultiple"
      text
      size="tiny"
      class="lead-comments-cell__toggle"
      @click="expanded = !expanded"
    >
      {{ expanded ? 'Свернуть' : `Ещё ${hiddenCount}` }}
    </NButton>
    <ul v-if="expanded && hasMultiple" class="lead-comments-cell__list">
      <li v-for="item in sorted" :key="item.id" class="lead-comments-cell__item">
        <span class="lead-comments-cell__item-text">{{ item.body }}</span>
        <span class="lead-comments-cell__item-meta">{{ formatWhen(item.created_at) }}</span>
      </li>
    </ul>
  </div>
  <span v-else class="lead-comments-cell__empty">—</span>
</template>

<style scoped>
.lead-comments-cell__text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.lead-comments-cell__meta {
  display: block;
  margin-top: 4px;
  font-size: 0.75rem;
  opacity: 0.65;
}

.lead-comments-cell__toggle {
  margin-top: 4px;
  padding: 0;
}

.lead-comments-cell__list {
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
}

.lead-comments-cell__item {
  padding: 6px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}

.lead-comments-cell__item-text {
  display: block;
  white-space: pre-wrap;
  word-break: break-word;
}

.lead-comments-cell__item-meta {
  display: block;
  margin-top: 2px;
  font-size: 0.75rem;
  opacity: 0.65;
}

.lead-comments-cell__empty {
  opacity: 0.55;
}
</style>
