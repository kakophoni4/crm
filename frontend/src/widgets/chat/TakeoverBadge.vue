<script setup lang="ts">
import { NAlert, NButton } from 'naive-ui'
import { computed } from 'vue'

import type { TakeoverState } from '@/entities/chat/types'
import { releaseTakeover } from '@/features/chats/api'
import { useAuthStore } from '@/shared/store/auth'

const props = defineProps<{
  takeover: TakeoverState | null
  chatId: number | null
}>()

const emit = defineEmits<{
  released: []
}>()

const auth = useAuthStore()

const isTakeoverSenior = computed(
  () => props.takeover && auth.user?.id === props.takeover.senior_user_id,
)

const label = computed(() => {
  if (!props.takeover) return ''
  if (isTakeoverSenior.value) {
    return 'Вы подключены к чату (takeover активен)'
  }
  return `Сейчас в чате руководитель (ID ${props.takeover.senior_user_id})`
})

async function release(): Promise<void> {
  if (!props.chatId) return
  await releaseTakeover(props.chatId)
  emit('released')
}
</script>

<template>
  <NAlert v-if="takeover" type="warning" :title="label" class="takeover-badge" :bordered="false">
    <NButton v-if="isTakeoverSenior" size="tiny" quaternary @click="release">
      Отключиться
    </NButton>
  </NAlert>
</template>

<style scoped>
.takeover-badge {
  flex-shrink: 0;
  margin: 0;
  border-radius: 0;
}
</style>
