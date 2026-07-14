<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

onMounted(() => {
  void router.replace({ name: 'notifications', query: { tab: 'history' } })
})
</script>

<template>
  <div />
</template>
