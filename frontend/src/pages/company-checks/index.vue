<script setup lang="ts">
import { FileCheck2 } from 'lucide-vue-next'
import CompanyChecks from '@/features/lavok-parser/CompanyChecks.vue'
</script>

<template>
  <section class="company-checks-page">
    <header>
      <h1><FileCheck2 :size="24" /> Проверка компаний</h1>
      <p>Проверка вашей базы по Excel. Задания и отчёты хранятся отдельно от объявлений продавцов.</p>
    </header>
    <CompanyChecks />
  </section>
</template>

<style scoped>
.company-checks-page{display:grid;gap:18px;min-width:0}.company-checks-page h1{display:flex;align-items:center;gap:10px;margin:0;font-size:24px}.company-checks-page header p{margin:8px 0 0;color:var(--app-text-muted,#888);line-height:1.5}
</style>
