<script setup lang="ts">
withDefaults(defineProps<{ collapsed?: boolean }>(), { collapsed: false })
</script>

<template>
  <div class="brand-mark" :class="{ 'brand-mark--collapsed': collapsed }">
    <img
      class="brand-mark__logo"
      src="/brand/logo.png"
      alt=""
      draggable="false"
    />
  </div>
</template>

<style scoped>
.brand-mark {
  display: flex;
  align-items: center;
  min-width: 0;
  height: 100%;
}

.brand-mark--collapsed {
  justify-content: center;
  width: 100%;
}

.brand-mark__logo {
  display: block;
  height: 36px;
  width: auto;
  max-width: 100%;
  object-fit: contain;
  user-select: none;
}

.brand-mark--collapsed .brand-mark__logo {
  height: 28px;
  width: 28px;
  object-fit: cover;
  object-position: center;
  border-radius: 6px;
}
</style>
