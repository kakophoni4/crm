import { flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import { registerChatListSearchFocus } from '@/features/chats/chat-list-search-focus'
import AppLayout from '@/widgets/app-layout/AppLayout.vue'

vi.mock('@vueuse/core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@vueuse/core')>()
  return {
    ...actual,
    useWindowSize: () => ({ width: ref(1200) }),
  }
})

function dispatchKey(key: string, init: KeyboardEventInit = {}): void {
  window.dispatchEvent(
    new KeyboardEvent('keydown', {
      key,
      bubbles: true,
      ...init,
    }),
  )
}

async function mountLayout(initialPath = '/chats') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/chats', name: 'chats', component: { template: '<div class="chats-stub" />' } },
      { path: '/contacts', name: 'contacts', component: { template: '<div />' } },
    ],
  })
  await router.push(initialPath)

  const Host = defineComponent({
    setup() {
      return () =>
        h(NConfigProvider, null, () =>
          h(NMessageProvider, null, () => h(AppLayout)),
        )
    },
  })

  const wrapper = mount(Host, {
    attachTo: document.body,
    global: {
      plugins: [pinia, router],
      stubs: { RouterView: true },
    },
  })
  await flushPromises()
  return wrapper
}

let layoutWrapper: ReturnType<typeof mount> | null = null

describe('app hotkeys', () => {
  beforeEach(() => {
    registerChatListSearchFocus(null)
  })

  afterEach(() => {
    layoutWrapper?.unmount()
    layoutWrapper = null
    document.body.innerHTML = ''
  })

  it('opens global search on Ctrl+K', async () => {
    layoutWrapper = await mountLayout('/contacts')

    expect(document.querySelector('[aria-label="Глобальный поиск"]')).toBeNull()

    dispatchKey('k', { ctrlKey: true })
    await flushPromises()

    expect(document.querySelector('[aria-label="Глобальный поиск"]')).toBeTruthy()
  })

  it('opens global search on Meta+K', async () => {
    layoutWrapper = await mountLayout('/contacts')

    dispatchKey('k', { metaKey: true })
    await flushPromises()

    expect(document.querySelector('[aria-label="Глобальный поиск"]')).toBeTruthy()
  })

  it('focuses chat list search on / when on chats route', async () => {
    const focusMock = vi.fn()
    registerChatListSearchFocus(focusMock)

    layoutWrapper = await mountLayout('/chats')

    dispatchKey('/')
    await flushPromises()

    expect(focusMock).toHaveBeenCalledTimes(1)
  })

  it('does not focus chat search on / when not on chats route', async () => {
    const focusMock = vi.fn()
    registerChatListSearchFocus(focusMock)

    layoutWrapper = await mountLayout('/contacts')

    dispatchKey('/')
    await flushPromises()

    expect(focusMock).not.toHaveBeenCalled()
  })

  it('closes global search on Escape', async () => {
    layoutWrapper = await mountLayout('/contacts')

    dispatchKey('k', { ctrlKey: true })
    await flushPromises()
    expect(document.querySelector('.n-modal-mask')).toBeTruthy()

    dispatchKey('Escape')
    await flushPromises()

    expect(document.querySelector('.n-modal-mask')).toBeNull()
  })
})
