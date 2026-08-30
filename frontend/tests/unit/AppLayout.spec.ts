import { mount } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import AppLayout from '@/widgets/app-layout/AppLayout.vue'
import { useThemeStore } from '@/shared/store/theme'

const windowWidth = ref(1200)

vi.mock('@vueuse/core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@vueuse/core')>()
  return {
    ...actual,
    useWindowSize: () => ({ width: windowWidth }),
  }
})

function mountAppLayout() {
  const pinia = createPinia()
  setActivePinia(pinia)
  useThemeStore().setPreference('light')
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'dashboard', component: { template: '<div />' } },
      { path: '/chats', name: 'chats', component: { template: '<div />' } },
    ],
  })
  const Host = defineComponent({
    setup() {
      return () =>
        h(NConfigProvider, null, () =>
          h(NMessageProvider, null, () => h(AppLayout)),
        )
    },
  })

  return mount(Host, {
    global: {
      plugins: [pinia, router],
      stubs: { RouterView: true },
    },
  })
}

describe('AppLayout', () => {
  beforeEach(() => {
    document.documentElement.classList.remove('dark')
    windowWidth.value = 1200
  })

  it('mounts layout shell', () => {
    const layout = mountAppLayout()
    expect(layout.find('.app-layout').exists()).toBe(true)
    expect(layout.find('.app-topbar').exists()).toBe(true)
    expect(layout.find('.app-sidebar').exists()).toBe(true)
    layout.unmount()
  })

  it('toggles theme via topbar control', async () => {
    const layout = mountAppLayout()
    const themeStore = useThemeStore()

    expect(themeStore.isDark).toBe(false)

    await layout.find('[aria-label="Переключить тему"]').trigger('click')

    expect(themeStore.isDark).toBe(true)
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    layout.unmount()
  })

  it('hides sidebar on a phone for managers', () => {
    windowWidth.value = 390
    const layout = mountAppLayout()
    expect(layout.find('.app-layout--phone-chats').exists()).toBe(true)
    expect(layout.find('.app-sidebar').exists()).toBe(false)
    expect(layout.find('.app-topbar').exists()).toBe(true)
    layout.unmount()
  })
})
