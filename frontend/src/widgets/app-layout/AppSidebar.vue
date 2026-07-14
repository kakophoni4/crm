<script setup lang="ts">
import {
  Bot,
  Calculator,
  ClipboardList,
  FolderOpen,
  CheckSquare,
  LayoutDashboard,
  MessageSquare,
  Phone,
  Settings,
  Shield,
  Tags,
  UserPlus,
  Users,
  UsersRound,
  Moon,
  Bell,
} from 'lucide-vue-next'
import { NDrawer, NDrawerContent, NIcon, NLayoutSider, NMenu, NSelect } from 'naive-ui'
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { listTelephonyAccounts } from '@/features/telephony/api'
import { useAuthStore } from '@/shared/store/auth'
import { useThemeStore, type ThemePreference } from '@/shared/store/theme'
import BrandMark from './BrandMark.vue'

defineProps<{
  collapsed: boolean
  mobile: boolean
  drawerVisible: boolean
}>()

const emit = defineEmits<{
  toggle: []
  closeDrawer: []
}>()

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const themeStore = useThemeStore()
const telephonyVisible = ref(false)

const themeOptions = [
  { label: 'Светлая', value: 'light' as ThemePreference },
  { label: 'Тёмная', value: 'dark' as ThemePreference },
  { label: 'Системная', value: 'system' as ThemePreference },
]

const canRequestTelephony = computed(
  () => auth.user?.permissions.includes('telephony.call') === true,
)

async function refreshTelephonyVisibility(): Promise<void> {
  if (!canRequestTelephony.value) {
    telephonyVisible.value = false
    return
  }
  try {
    const accounts = await listTelephonyAccounts()
    telephonyVisible.value = accounts.some((account) => account.is_active)
  } catch {
    telephonyVisible.value = false
  }
}

const menuOptions = computed(() => {
  if (auth.isAccountant) {
    return [
      {
        label: 'Бухгалтерия',
        key: 'accounting',
        icon: () => h(NIcon, null, { default: () => h(Calculator) }),
      },
    ]
  }

  const items = [
  {
    label: 'Чаты',
    key: 'chats',
    icon: () => h(NIcon, null, { default: () => h(MessageSquare) }),
  },
  {
    label: 'Контакты',
    key: 'contacts',
    icon: () => h(NIcon, null, { default: () => h(Users) }),
  },
  {
    label: 'Заявки',
    key: 'applications',
    icon: () => h(NIcon, null, { default: () => h(ClipboardList) }),
  },
  {
    label: 'Хранилище',
    key: 'storage',
    icon: () => h(NIcon, null, { default: () => h(FolderOpen) }),
  },
  {
    label: 'Задачи',
    key: 'tasks',
    icon: () => h(NIcon, null, { default: () => h(CheckSquare) }),
  },
  {
    label: 'Уведомления',
    key: 'notifications',
    icon: () => h(NIcon, null, { default: () => h(Bell) }),
  },
  {
    label: 'Dashboard',
    key: 'dashboard',
    icon: () => h(NIcon, null, { default: () => h(LayoutDashboard) }),
  },
  ]

  if (telephonyVisible.value) {
    items.splice(2, 0, {
      label: 'Телефония',
      key: 'telephony',
      icon: () => h(NIcon, null, { default: () => h(Phone) }),
    })
  }

  if (auth.user?.role === 'senior' || auth.user?.role === 'group_senior' || auth.user?.role === 'admin') {
    items.push({
      label: 'Эскалация',
      key: 'group-escalation',
      icon: () => h(NIcon, null, { default: () => h(Settings) }),
    })
    items.push({
      label: 'Статусы',
      key: 'admin-statuses',
      icon: () => h(NIcon, null, { default: () => h(Tags) }),
    })
  }

  if (auth.user?.role === 'senior' || auth.user?.role === 'admin') {
    items.push({
      label: 'Автоответчик',
      key: 'group-after-hours',
      icon: () => h(NIcon, null, { default: () => h(Moon) }),
    })
  }

  if (auth.user?.role === 'senior' || auth.user?.role === 'group_senior') {
    items.push({
      label: 'Пользователи',
      key: 'settings-users',
      icon: () => h(NIcon, null, { default: () => h(UserPlus) }),
    })
    items.push({
      label: 'Группы',
      key: 'settings-groups',
      icon: () => h(NIcon, null, { default: () => h(UsersRound) }),
    })
    items.push({
      label: 'Боты',
      key: 'settings-bots',
      icon: () => h(NIcon, null, { default: () => h(Bot) }),
    })
    items.push({
      label: 'Настройки телефонии',
      key: 'settings-telephony',
      icon: () => h(NIcon, null, { default: () => h(Phone) }),
    })
  }

  if (auth.isAdmin) {
    items.push({
      label: 'Админка',
      key: 'admin',
      icon: () => h(NIcon, null, { default: () => h(Shield) }),
    })
  }

  if (auth.canAccounting) {
    items.push({
      label: 'Бухгалтерия',
      key: 'accounting',
      icon: () => h(NIcon, null, { default: () => h(Calculator) }),
    })
  }

  return items
})

const activeKey = computed(() => {
  if (route.name === 'chats') return 'chats'
  if (route.name === 'contacts' || route.name === 'contact-detail') return 'contacts'
  if (route.name === 'applications') return 'applications'
  if (route.name === 'storage') return 'storage'
  if (route.name === 'tasks') return 'tasks'
  if (route.name === 'notifications' || route.name === 'notification-history') return 'notifications'
  if (route.name === 'accounting') return 'accounting'
  if (route.name === 'telephony') return 'telephony'
  if (route.name === 'dashboard') return 'dashboard'
  if (route.name === 'group-escalation') return 'group-escalation'
  if (route.name === 'group-after-hours') return 'group-after-hours'
  if (route.name === 'admin-statuses') return 'admin-statuses'
  if (route.name === 'settings-users') return 'settings-users'
  if (route.name === 'settings-groups') return 'settings-groups'
  if (route.name === 'settings-bots') return 'settings-bots'
  if (route.name === 'settings-telephony') return 'settings-telephony'
  if (typeof route.name === 'string' && route.name.startsWith('admin')) return 'admin'
  return null
})

function onMenuUpdate(key: string): void {
  if (key === 'chats') {
    void router.push({ name: 'chats' })
    emit('closeDrawer')
    return
  }
  if (key === 'contacts') {
    void router.push({ name: 'contacts' })
    emit('closeDrawer')
    return
  }
  if (key === 'applications') {
    void router.push({ name: 'applications' })
    emit('closeDrawer')
    return
  }
  if (key === 'storage') {
    void router.push({ name: 'storage' })
    emit('closeDrawer')
    return
  }
  if (key === 'tasks') {
    void router.push({ name: 'tasks' })
    emit('closeDrawer')
    return
  }
  if (key === 'notifications') {
    void router.push({ name: 'notifications' })
    emit('closeDrawer')
    return
  }
  if (key === 'accounting') {
    void router.push({ name: 'accounting' })
    emit('closeDrawer')
    return
  }
  if (key === 'telephony') {
    void router.push({ name: 'telephony' })
    emit('closeDrawer')
    return
  }
  if (key === 'dashboard') {
    void router.push({ name: 'dashboard' })
    emit('closeDrawer')
    return
  }
  if (key === 'group-escalation') {
    const escalationGroupId =
      auth.user?.group_ids?.[0] ?? auth.user?.group_id ?? undefined
    const query =
      escalationGroupId != null ? { group_id: String(escalationGroupId) } : undefined
    void router.push({ name: 'group-escalation', query })
    emit('closeDrawer')
    return
  }
  if (key === 'group-after-hours') {
    void router.push({ name: 'group-after-hours' })
    emit('closeDrawer')
    return
  }
  if (key === 'admin-statuses') {
    void router.push({ name: 'admin-statuses' })
    emit('closeDrawer')
    return
  }
  if (key === 'settings-users') {
    void router.push({ name: 'settings-users' })
    emit('closeDrawer')
    return
  }
  if (key === 'settings-groups') {
    void router.push({ name: 'settings-groups' })
    emit('closeDrawer')
    return
  }
  if (key === 'settings-bots') {
    void router.push({ name: 'settings-bots' })
    emit('closeDrawer')
    return
  }
  if (key === 'settings-telephony') {
    void router.push({ name: 'settings-telephony' })
    emit('closeDrawer')
    return
  }
  if (key === 'admin') {
    void router.push({ name: 'admin' })
    emit('closeDrawer')
  }
}

const sidebarWidth = 240
const collapsedWidth = 64

onMounted(() => {
  void refreshTelephonyVisibility()
  window.addEventListener('telephony-accounts-changed', refreshTelephonyVisibility)
})

onBeforeUnmount(() => {
  window.removeEventListener('telephony-accounts-changed', refreshTelephonyVisibility)
})

watch(
  () => auth.user?.permissions.join(',') ?? '',
  () => {
    void refreshTelephonyVisibility()
  },
)
</script>

<template>
  <NDrawer
    v-if="mobile"
    :show="drawerVisible"
    placement="left"
    :width="sidebarWidth"
    @update:show="(v: boolean) => !v && emit('closeDrawer')"
  >
    <NDrawerContent body-content-style="padding: 0">
      <div class="app-sidebar app-sidebar--drawer">
        <div class="app-sidebar__brand">
          <BrandMark />
        </div>
        <NMenu
          :value="activeKey"
          :options="menuOptions"
          @update:value="onMenuUpdate"
        />
        <div class="app-sidebar__theme">
          <span class="app-sidebar__theme-label">Тема</span>
          <NSelect
            :value="themeStore.preference"
            :options="themeOptions"
            size="small"
            aria-label="Тема оформления"
            @update:value="(v: ThemePreference) => themeStore.setPreference(v)"
          />
        </div>
      </div>
    </NDrawerContent>
  </NDrawer>

  <NLayoutSider
    v-else
    bordered
    collapse-mode="width"
    :collapsed="collapsed"
    :collapsed-width="collapsedWidth"
    :width="sidebarWidth"
    class="app-sidebar"
    show-trigger="arrow-circle"
    @collapse="emit('toggle')"
    @expand="emit('toggle')"
  >
    <div class="app-sidebar__brand" :class="{ 'app-sidebar__brand--collapsed': collapsed }">
      <BrandMark :collapsed="collapsed" />
    </div>
    <NMenu :value="activeKey" :options="menuOptions" @update:value="onMenuUpdate" />
    <div class="app-sidebar__theme">
      <span class="app-sidebar__theme-label">Тема</span>
      <NSelect
        :value="themeStore.preference"
        :options="themeOptions"
        size="small"
        aria-label="Тема оформления"
        @update:value="(v: ThemePreference) => themeStore.setPreference(v)"
      />
    </div>
  </NLayoutSider>
</template>

<style scoped>
.app-sidebar {
  background: var(--app-surface);
}

.app-sidebar__brand {
  display: flex;
  align-items: center;
  height: var(--app-topbar-height);
  padding: 0 16px;
  border-bottom: 1px solid var(--app-border);
  overflow: hidden;
}

.app-sidebar__brand--collapsed {
  padding: 0;
  justify-content: center;
}

.app-sidebar__theme {
  margin-top: auto;
  padding: 12px 16px 16px;
  border-top: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.app-sidebar__theme-label {
  font-size: 0.75rem;
  color: var(--app-text-muted);
}

.app-sidebar--drawer {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}
</style>
