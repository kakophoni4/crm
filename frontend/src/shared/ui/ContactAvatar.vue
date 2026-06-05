<script setup lang="ts">
import { computed } from 'vue'

import { avatarColorFromId, getContactInitials } from '@/shared/lib/avatar'

const props = withDefaults(
  defineProps<{
    contactId: number | string
    fullName: string
    size?: number
  }>(),
  { size: 36 },
)

const initials = computed(() => getContactInitials(props.fullName))
const backgroundColor = computed(() => avatarColorFromId(props.contactId))
const fontSize = computed(() => Math.max(10, Math.round(props.size * 0.38)))
</script>

<template>
  <span
    class="contact-avatar"
    :style="{
      width: `${size}px`,
      height: `${size}px`,
      fontSize: `${fontSize}px`,
      backgroundColor,
    }"
    role="img"
    :aria-label="fullName"
  >
    {{ initials }}
  </span>
</template>

<style scoped>
.contact-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 50%;
  color: #fff;
  font-weight: 600;
  line-height: 1;
  user-select: none;
}
</style>
