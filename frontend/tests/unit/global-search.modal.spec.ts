import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { defineComponent, h } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import GlobalSearchModal from '@/features/search/GlobalSearchModal.vue'
import type { GlobalSearchResponse } from '@/features/search/types'

const globalSearchMock = vi.fn()

vi.mock('@/features/search/api', () => ({
  globalSearch: (...args: unknown[]) => globalSearchMock(...args),
}))

const sampleResponse: GlobalSearchResponse = {
  contacts: {
    items: [
      {
        id: 7,
        full_name: 'Анна Смирнова',
        phone: '+79001112233',
        email: null,
        telegram_username: 'anna_s',
        status: 'active',
        custom_fields: {},
        assigned_department_id: 1,
        source: 'manual',
        archived_at: null,
        created_by: 1,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-02T00:00:00Z',
      },
    ],
    next_cursor: null,
  },
  messages: {
    items: [
      {
        chat_id: 101,
        contact_id: 7,
        message_id: 555,
        snippet: 'Договорились о <mark>поставке</mark>',
        matched_at: '2026-05-17T12:00:00Z',
      },
    ],
    next_cursor: null,
  },
  chats: {
    items: [
      {
        id: 101,
        contact_id: 7,
        contact_name: 'Анна Смирнова',
        bot_id: 1,
        assigned_user_id: 2,
        assigned_group_id: 3,
        assigned_department_id: 1,
        status: 'open',
        status_id: null,
        last_message_at: '2026-05-17T12:00:00Z',
        last_message_preview: 'Последнее сообщение',
      },
    ],
    next_cursor: null,
  },
}

let modalWrapper: ReturnType<typeof mount> | null = null
let router: Router

async function mountModal(show = true): Promise<void> {
  const pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: { template: '<div />' } },
      { path: '/contacts/:id', name: 'contact-detail', component: { template: '<div />' } },
      { path: '/chats', name: 'chats', component: { template: '<div />' } },
    ],
  })
  await router.push('/')

  const Host = defineComponent({
    setup() {
      return () =>
        h(NConfigProvider, null, () =>
          h(NMessageProvider, null, () =>
            h(GlobalSearchModal, {
              show,
              'onUpdate:show': () => undefined,
            }),
          ),
        )
    },
  })

  modalWrapper = mount(Host, {
    attachTo: document.body,
    global: {
      plugins: [pinia, router],
    },
  })
  await flushPromises()
}

function searchInput(): DOMWrapper<HTMLInputElement> {
  const el = document.querySelector('input.n-input__input-el')
  if (!el) throw new Error('search input not found')
  return new DOMWrapper(el as HTMLInputElement)
}

function modalComponent() {
  return modalWrapper!.findComponent(GlobalSearchModal)
}

describe('GlobalSearchModal', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    globalSearchMock.mockReset()
    globalSearchMock.mockResolvedValue(sampleResponse)
  })

  afterEach(() => {
    vi.useRealTimers()
    modalWrapper?.unmount()
    modalWrapper = null
    document.body.innerHTML = ''
  })

  it('renders with aria-label and debounced search', async () => {
    await mountModal()
    expect(document.querySelector('[aria-label="Глобальный поиск"]')).toBeTruthy()

    await searchInput().setValue('анна')
    vi.advanceTimersByTime(300)
    await flushPromises()

    expect(globalSearchMock).toHaveBeenCalledWith({ q: 'анна', limit_per_type: 10 })
    expect(document.body.textContent).toContain('Анна Смирнова')
  })

  it('navigates to contact on click', async () => {
    await mountModal()

    await searchInput().setValue('анна')
    vi.advanceTimersByTime(300)
    await flushPromises()

    const result = document.querySelector('.global-search-modal__result') as HTMLElement
    result.click()
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('contact-detail')
    expect(router.currentRoute.value.params.id).toBe('7')
  })

  it('navigates to chat from messages tab', async () => {
    await mountModal()

    await searchInput().setValue('постав')
    vi.advanceTimersByTime(300)
    await flushPromises()

    const tabs = Array.from(document.querySelectorAll('.n-tabs-tab'))
    const messagesTab = tabs.find((tab) => tab.textContent?.includes('Сообщения'))
    expect(messagesTab).toBeTruthy()
    messagesTab!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await nextTick()
    await flushPromises()

    const result = document.querySelector('.global-search-modal__result') as HTMLElement
    result.click()
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('chats')
    expect(router.currentRoute.value.query.chatId).toBe('101')
  })

  it('does not search when query shorter than 2 chars', async () => {
    await mountModal()

    await searchInput().setValue('а')
    vi.advanceTimersByTime(300)
    await flushPromises()

    expect(globalSearchMock).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('минимум 2 символа')
  })

  it('closes on Escape key in input', async () => {
    await mountModal()

    await searchInput().trigger('keydown', { key: 'Escape' })
    expect(modalComponent().emitted('update:show')?.[0]).toEqual([false])
  })
})
