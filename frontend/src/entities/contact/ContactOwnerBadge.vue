<script setup lang="ts">

import { NTag } from 'naive-ui'

import { computed } from 'vue'



const props = defineProps<{

  ownerFullName?: string | null

  ownerUserId?: number | null

  escalated?: boolean

  pending?: boolean

  size?: 'small' | 'medium' | 'large'

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

  <NTag :type="tagType" :size="size ?? 'small'" round :bordered="false" class="contact-owner-badge">

    Владелец: {{ label }}

  </NTag>

</template>


