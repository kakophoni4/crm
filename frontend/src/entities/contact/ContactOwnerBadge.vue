<script setup lang="ts">
import { NTag, NTooltip } from 'naive-ui'
import { computed } from 'vue'

const props = defineProps<{
  ownerFullName?: string | null
  ownerUserId?: number | null
  escalated?: boolean
  pending?: boolean
  size?: 'small' | 'medium' | 'large'
  /** In chat header: owner name only, full label in tooltip */
  compact?: boolean
}>()

const label = computed(() => {
  if (props.ownerFullName?.trim()) return props.ownerFullName.trim()
  if (props.ownerUserId != null) return `#${props.ownerUserId}`
  return 'Не назначен'
})

const tagType = computed(() => {
  if (props.escalated) return 'error' as const
  if (props.pending) return 'warning' as const
  return 'default' as const
})
</script>

<template>
  <NTooltip v-if="compact">
    <template #trigger>
      <NTag :type="tagType" :size="size ?? 'small'" round :bordered="false" class="contact-owner-badge">
        {{ label }}
      </NTag>
    </template>
    Владелец: {{ label }}
  </NTooltip>
  <NTag
    v-else
    :type="tagType"
    :size="size ?? 'small'"
    round
    :bordered="false"
    class="contact-owner-badge"
  >
    Владелец: {{ label }}
  </NTag>
</template>
