<script setup lang="ts">
import { NButton, NResult } from 'naive-ui'
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <NResult status="404" title="Страница не найдена" description="Запрошенный маршрут не существует.">
    <template #footer>
      <NButton type="primary" @click="router.push({ name: 'dashboard' })">
        На главную
      </NButton>
    </template>
  </NResult>
</template>
