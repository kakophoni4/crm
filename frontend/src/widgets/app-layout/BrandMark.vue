<script setup lang="ts">
withDefaults(defineProps<{ collapsed?: boolean }>(), { collapsed: false })
</script>

<template>
  <div class="brand-mark" :class="{ 'brand-mark--collapsed': collapsed }">
    <span class="brand-mark__badge" aria-hidden="true">X</span>
    <span v-if="!collapsed" class="brand-mark__text">ХУИтРИКС</span>
  </div>
</template>

<style scoped>
.brand-mark {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.brand-mark--collapsed {
  gap: 0;
  justify-content: center;
}

.brand-mark__badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--app-accent);
  color: #ffffff;
  font-weight: 700;
  font-size: 0.875rem;
  line-height: 1;
}

.brand-mark__text {
  font-weight: 700;
  font-size: 1rem;
  letter-spacing: -0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
