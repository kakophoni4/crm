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
import { NDrawer, NDrawerContent, NIcon, NLayoutSider, NMenu } from 'naive-ui'
import { computed, h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchRequirementsDueSummary } from '@/features/accounting/api'
import { fetchTaskAlerts } from '@/features/tasks/api'
import { listTelephonyAccounts } from '@/features/telephony/api'
import { useAuthStore } from '@/shared/store/auth'
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

const canRequestTelephony = computed(
  () => auth.user?.permissions.includes('telephony.call') === true,
)

/** Show immediately by permission; refine after accounts load (avoids late menu pop-in). */
const telephonyVisible = ref(canRequestTelephony.value)

async function refreshTelephonyVisibility(): Promise<void> {
  if (!canRequestTelephony.value) {
    telephonyVisible.value = false
    return
  }
  telephonyVisible.value = true
  try {
    const accounts = await listTelephonyAccounts()
    telephonyVisible.value = accounts.some((account) => account.is_active)
  } catch {
    // Keep visible on transient errors — route guard still checks accounts.
  }
}

const tasksBlink = ref(false)
const accountingBlink = ref(false)
let alertsTimer: ReturnType<typeof setInterval> | null = null

async function refreshAlerts(): Promise<void> {
  try {
    if (auth.user?.permissions?.includes('tasks.read')) {
      const alerts = await fetchTaskAlerts()
      tasksBlink.value = alerts.blink
    } else {
      tasksBlink.value = false
    }
  } catch {
    /* ignore */
  }
  try {
    if (auth.canAccounting) {
      const due = await fetchRequirementsDueSummary()
      accountingBlink.value = due.overdue > 0 || due.due_soon > 0
    } else {
      accountingBlink.value = false
    }
  } catch {
    /* ignore */
  }
}

function blinkIcon(icon: unknown, blink: boolean) {
  return () =>
    h(
      NIcon,
      { class: blink ? 'sidebar-blink' : undefined },
      { default: () => h(icon as typeof CheckSquare) },
    )
}

const menuOptions = computed(() => {
  if (auth.isAccountant) {
    return [
      {
        label: 'Бухгалтерия',
        key: 'accounting',
        icon: blinkIcon(Calculator, accountingBlink.value),
      },
      {
        label: 'Задачи',
        key: 'tasks',
        icon: blinkIcon(CheckSquare, tasksBlink.value),
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
    icon: blinkIcon(CheckSquare, tasksBlink.value),
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
      icon: blinkIcon(Calculator, accountingBlink.value),
    })
  }

  return items
})

watch(
  () => auth.user?.id,
  () => {
    void refreshAlerts()
  },
)

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
    void router.push({ name: 'notifications', query: { tab: 'history' } })
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
  void refreshAlerts()
  alertsTimer = setInterval(() => {
    void refreshAlerts()
  }, 60000)
  window.addEventListener('telephony-accounts-changed', refreshTelephonyVisibility)
})

onBeforeUnmount(() => {
  if (alertsTimer) clearInterval(alertsTimer)
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
        <div class="app-sidebar__menu">
          <NMenu
            :value="activeKey"
            :options="menuOptions"
            @update:value="onMenuUpdate"
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
    <div class="app-sidebar__inner">
      <div class="app-sidebar__brand" :class="{ 'app-sidebar__brand--collapsed': collapsed }">
        <BrandMark :collapsed="collapsed" />
      </div>
      <div class="app-sidebar__menu">
        <NMenu :value="activeKey" :options="menuOptions" @update:value="onMenuUpdate" />
      </div>
    </div>
  </NLayoutSider>
</template>

<style scoped>
.app-sidebar {
  background: var(--app-surface);
  height: 100vh !important;
  max-height: 100vh;
  position: sticky !important;
  top: 0;
  align-self: flex-start;
}

.app-sidebar :deep(.n-layout-sider-scroll-container) {
  height: 100vh;
  max-height: 100vh;
  overflow: hidden;
}

.app-sidebar__inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.app-sidebar__brand {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--app-topbar-height);
  padding: 0 12px;
  border-bottom: 1px solid var(--app-border);
  overflow: hidden;
}

.app-sidebar__brand--collapsed {
  padding: 0;
}

.app-sidebar__menu {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.app-sidebar--drawer {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 100%;
}

:deep(.sidebar-blink) {
  color: #dc2626 !important;
  animation: sidebar-due-pulse 1.6s ease-in-out infinite;
}

@keyframes sidebar-due-pulse {
  0%,
  100% {
    opacity: 1;
    filter: drop-shadow(0 0 0 transparent);
  }
  50% {
    opacity: 0.45;
    filter: drop-shadow(0 0 4px rgba(220, 38, 38, 0.65));
  }
}
</style>
