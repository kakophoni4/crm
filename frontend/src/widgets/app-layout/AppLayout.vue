<script setup lang="ts">
import { useWindowSize } from '@vueuse/core'
import { NLayout, NLayoutContent } from 'naive-ui'
import { computed, ref, watch } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import GlobalSearchModal from '@/features/search/GlobalSearchModal.vue'
import { useAppHotkeys } from '@/features/search/useAppHotkeys'
import {
  isPhoneChatsAllowedRoute,
  PHONE_MAX_WIDTH,
  usePhoneChatsOnly,
} from '@/shared/lib/phone-mode'
import AppSidebar from '@/widgets/app-layout/AppSidebar.vue'
import AppTopbar from '@/widgets/app-layout/AppTopbar.vue'
import IdleContractBanner from '@/widgets/app-layout/IdleContractBanner.vue'

const globalSearchOpen = ref(false)
useAppHotkeys(globalSearchOpen)

const { width } = useWindowSize()
const isMobile = computed(() => width.value <= PHONE_MAX_WIDTH)
const phoneChatsOnly = usePhoneChatsOnly()
const route = useRoute()
const router = useRouter()
const sidebarCollapsed = ref(false)
const drawerVisible = ref(false)

watch(
  [phoneChatsOnly, () => route.name],
  ([phoneOnly, name]) => {
    if (phoneOnly && !isPhoneChatsAllowedRoute(name)) {
      void router.replace({ name: 'chats' })
    }
  },
  { immediate: true },
)

function toggleSidebar(): void {
  if (phoneChatsOnly.value) return
  if (isMobile.value) {
    drawerVisible.value = !drawerVisible.value
    return
  }
  sidebarCollapsed.value = !sidebarCollapsed.value
}
</script>

<template>
  <NLayout
    class="app-layout"
    :class="{ 'app-layout--phone-chats': phoneChatsOnly }"
    :has-sider="!phoneChatsOnly"
  >
    <AppSidebar
      v-if="!phoneChatsOnly"
      :collapsed="sidebarCollapsed"
      :mobile="isMobile"
      :drawer-visible="drawerVisible"
      @toggle="toggleSidebar"
      @close-drawer="drawerVisible = false"
    />
    <NLayout class="app-layout__main">
      <AppTopbar
        :show-menu-button="isMobile && !phoneChatsOnly"
        :phone-chats="phoneChatsOnly"
        @toggle-sidebar="toggleSidebar"
      >
        <template #left>
          <span v-if="phoneChatsOnly" class="app-layout__phone-title">Чаты</span>
          <slot v-else name="topbar-left" />
        </template>
        <template #right>
          <slot name="topbar-right" />
        </template>
      </AppTopbar>
      <NLayoutContent
        class="app-layout__content"
        :content-style="phoneChatsOnly ? 'padding: 0' : 'padding: var(--app-content-padding)'"
      >
        <RouterView />
      </NLayoutContent>
    </NLayout>
    <GlobalSearchModal v-if="!phoneChatsOnly" v-model:show="globalSearchOpen" />
    <IdleContractBanner v-if="!phoneChatsOnly" />
  </NLayout>
</template>

<style scoped>
.app-layout {
  height: 100vh;
  max-height: 100vh;
  overflow: hidden;
  background: var(--app-bg);
}

.app-layout__main {
  height: 100vh;
  max-height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* Only the main column shell — do not lock nested content scroll. */
.app-layout__main > :deep(.n-layout-scroll-container) {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.app-layout__content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* Actual page scroll lives here (Naive wraps slot in this container). */
.app-layout__content :deep(.n-layout-scroll-container) {
  height: 100%;
  overflow: auto !important;
  overscroll-behavior: contain;
}

.app-layout--phone-chats .app-layout__content :deep(.n-layout-scroll-container) {
  overflow: hidden !important;
}

.app-layout__phone-title {
  font-weight: 600;
  font-size: 1rem;
}
</style>
