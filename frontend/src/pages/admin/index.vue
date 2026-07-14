<script setup lang="ts">
import { NCard, NGrid, NGridItem } from 'naive-ui'
import { RouterLink } from 'vue-router'

const links = [
  { name: 'admin-departments', label: 'Отделы', desc: 'Создание и редактирование отделов' },
  { name: 'admin-groups', label: 'Группы', desc: 'Группы внутри отделов' },
  { name: 'admin-users', label: 'Пользователи', desc: 'Учётные записи, роли, группы' },
  { name: 'admin-bots', label: 'Боты', desc: 'Интеграции, группы и ротация секретов' },
  { name: 'admin-notification-bot', label: 'Бот уведомлений', desc: 'Токен Telegram-бота' },
  { name: 'admin-statuses', label: 'Воронка сделок', desc: 'Этапы открытых сделок (лидов)' },
] as const
</script>

<template>
  <section class="admin-page">
    <header class="admin-page__header">
      <h1 class="admin-page__title">Админка</h1>
      <p class="admin-page__subtitle">Управление организацией и справочниками</p>
    </header>

    <NGrid :x-gap="16" :y-gap="16" cols="1 s:2 m:3">
      <NGridItem v-for="item in links" :key="item.name">
        <RouterLink :to="{ name: item.name }" class="admin-page__link">
          <NCard :title="item.label" size="small" hoverable>
            {{ item.desc }}
          </NCard>
        </RouterLink>
      </NGridItem>
    </NGrid>
  </section>
</template>

<style scoped>
.admin-page__header {
  margin-bottom: 20px;
}

.admin-page__title {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
}

.admin-page__subtitle {
  margin: 8px 0 0;
  color: var(--app-text-muted);
}

.admin-page__link {
  text-decoration: none;
  color: inherit;
  display: block;
}
</style>
