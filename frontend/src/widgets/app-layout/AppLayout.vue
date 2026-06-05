<script setup lang="ts">
import { useWindowSize } from '@vueuse/core'
import { NLayout, NLayoutContent } from 'naive-ui'
import { computed, ref } from 'vue'
import { RouterView } from 'vue-router'

import GlobalSearchModal from '@/features/search/GlobalSearchModal.vue'
import { useAppHotkeys } from '@/features/search/useAppHotkeys'
import AppSidebar from '@/widgets/app-layout/AppSidebar.vue'
import AppTopbar from '@/widgets/app-layout/AppTopbar.vue'

const globalSearchOpen = ref(false)
useAppHotkeys(globalSearchOpen)

const MOBILE_BREAKPOINT = 768

const { width } = useWindowSize()
const isMobile = computed(() => width.value <= MOBILE_BREAKPOINT)
const sidebarCollapsed = ref(false)
const drawerVisible = ref(false)

function toggleSidebar(): void {
  if (isMobile.value) {
    drawerVisible.value = !drawerVisible.value
    return
  }
  sidebarCollapsed.value = !sidebarCollapsed.value
}
</script>

<template>
  <NLayout class="app-layout" has-sider>
    <AppSidebar
      :collapsed="sidebarCollapsed"
      :mobile="isMobile"
      :drawer-visible="drawerVisible"
      @toggle="toggleSidebar"
      @close-drawer="drawerVisible = false"
    />
    <NLayout class="app-layout__main">
      <AppTopbar @toggle-sidebar="toggleSidebar">
        <template #left>
          <slot name="topbar-left" />
        </template>
        <template #right>
          <slot name="topbar-right" />
        </template>
      </AppTopbar>
      <NLayoutContent class="app-layout__content" content-style="padding: var(--app-content-padding)">
        <RouterView />
      </NLayoutContent>
    </NLayout>
    <GlobalSearchModal v-model:show="globalSearchOpen" />
  </NLayout>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  background: var(--app-bg);
}

.app-layout__main {
  min-height: 100vh;
}

.app-layout__content {
  min-height: calc(100vh - var(--app-topbar-height));
}
</style>
