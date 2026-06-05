<script setup lang="ts">
defineProps<{
  title?: string
}>()
</script>

<template>
  <section class="app-card">
    <header v-if="title || $slots.header" class="app-card__header">
      <slot name="header">
        <h2 v-if="title" class="app-card__title">{{ title }}</h2>
      </slot>
    </header>
    <div class="app-card__body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.app-card {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 12px;
  padding: 20px 24px;
}

.app-card__header {
  margin-bottom: 16px;
}

.app-card__title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
}
</style>
