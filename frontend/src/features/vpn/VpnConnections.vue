<script setup lang="ts">
defineProps<{ occupiedSlots: number; deviceLimit: number }>()
</script>
<template>
  <div class="vpn-connections">
    <strong>Занято {{ occupiedSlots }} из {{ deviceLimit }} подключений</strong>
  </div>
</template>
<style scoped>
.vpn-connections { display: grid; gap: 6px; margin: 12px 0; font-size: 13px; }
</style>
