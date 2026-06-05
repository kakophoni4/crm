<script setup lang="ts">
import { Menu, Moon, Sun, User } from 'lucide-vue-next'
import { NButton, NDropdown, NIcon, NLayoutHeader, NSpace } from 'naive-ui'
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/shared/store/auth'
import { useThemeStore } from '@/shared/store/theme'
import { disconnectContactsRealtime } from '@/shared/realtime/contacts-ws'

defineEmits<{
  toggleSidebar: []
}>()

const themeStore = useThemeStore()
const auth = useAuthStore()
const router = useRouter()

const themeIcon = computed(() => (themeStore.isDark ? Sun : Moon))

const userLabel = computed(() => auth.user?.full_name ?? auth.user?.email ?? 'Пользователь')

const userMenuOptions = computed(() => [
  { label: userLabel.value, key: 'profile', disabled: true },
  { label: 'Выйти', key: 'logout' },
])

async function onUserMenuSelect(key: string): Promise<void> {
  if (key !== 'logout') return
  disconnectContactsRealtime()
  await auth.logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <NLayoutHeader bordered class="app-topbar">
    <div class="app-topbar__left">
      <NButton quaternary circle aria-label="Меню" @click="$emit('toggleSidebar')">
        <template #icon>
          <NIcon><Menu /></NIcon>
        </template>
      </NButton>
      <slot name="left">
        <span class="app-topbar__logo">CRM Chat Center</span>
      </slot>
    </div>
    <div class="app-topbar__right">
      <slot name="right">
        <NSpace align="center" :size="8">
          <NButton quaternary circle aria-label="Переключить тему" @click="themeStore.toggle()">
            <template #icon>
              <NIcon :component="themeIcon" />
            </template>
          </NButton>
          <NDropdown :options="userMenuOptions" trigger="click" @select="onUserMenuSelect">
            <NButton quaternary circle aria-label="Меню пользователя">
              <template #icon>
                <NIcon><User /></NIcon>
              </template>
            </NButton>
          </NDropdown>
        </NSpace>
      </slot>
    </div>
  </NLayoutHeader>
</template>

<style scoped>
.app-topbar {
  height: var(--app-topbar-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  background: var(--app-surface);
}

.app-topbar__left,
.app-topbar__right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-topbar__logo {
  font-weight: 600;
  margin-left: 4px;
}
</style>
