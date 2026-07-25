import { mount, flushPromises } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import ContactsPage from '@/pages/contacts/index.vue'
import type { Contact } from '@/entities/contact/types'
import { useAuthStore } from '@/shared/store/auth'

const sampleContacts: Contact[] = [
  {
    id: 1,
    full_name: 'Иван Петров',
    phone: '+79001234567',
    email: 'ivan@example.com',
    telegram_username: 'ivan_p',
    status: 'active',
    custom_fields: { tier: 'gold' },
    assigned_department_id: 1,
    source: 'manual',
    archived_at: null,
    created_by: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
]

const listContactsMock = vi.fn()

vi.mock('@/features/contacts/api', () => ({
  listContacts: (...args: unknown[]) => listContactsMock(...args),
  createContact: vi.fn(),
}))

vi.mock('@/features/contacts/CreateContactDialog.vue', () => ({
  default: defineComponent({
    name: 'CreateContactDialog',
    props: ['show'],
    emits: ['update:show', 'created'],
    setup() {
      return () => null
    },
  }),
}))

vi.mock('@/shared/lib/query-invalidation', () => ({
  onContactsInvalidate: () => () => undefined,
}))

function mountContactsPage(role: 'admin' | 'user' = 'admin') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.$patch({
    accessToken: 'token',
    user: {
      id: 1,
      email: 'u@crm.local',
      full_name: 'User',
      role,
      department_id: 1,
      group_id: null,
      presence: 'online',
      permissions: ['contacts.read', 'contacts.create'],
    },
  })

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/contacts', name: 'contacts', component: ContactsPage }],
  })

  const Host = defineComponent({
    setup() {
      return () =>
        h(NConfigProvider, null, () =>
          h(NMessageProvider, null, () => h(ContactsPage)),
        )
    },
  })

  return mount(Host, {
    global: {
      plugins: [pinia, router],
    },
  })
}

describe('contacts list page', () => {
  beforeEach(() => {
    listContactsMock.mockReset()
    listContactsMock.mockResolvedValue({
      items: sampleContacts,
      next_cursor: null,
      has_more: false,
    })
  })

  it('renders table rows from API', async () => {
    const wrapper = mountContactsPage('admin')
    await flushPromises()

    expect(listContactsMock).toHaveBeenCalled()
    expect(wrapper.text()).toContain('Иван Петров')
    expect(wrapper.text()).toContain('TG user ID')
    wrapper.unmount()
  })

  it('hides telegram_user_id column for non-admin', async () => {
    const wrapper = mountContactsPage('user')
    await flushPromises()

    expect(wrapper.text()).toContain('Иван Петров')
    expect(wrapper.text()).not.toContain('TG user ID')
    wrapper.unmount()
  })

  it('shows create button when user can create contacts', async () => {
    const wrapper = mountContactsPage('admin')
    const auth = useAuthStore()
    auth.$patch({
      user: {
        ...auth.user!,
        permissions: ['contacts.read', 'contacts.create'],
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Создать контакт')
    wrapper.unmount()
  })

  it('hides create button without contacts.create permission', async () => {
    const wrapper = mountContactsPage('user')
    await flushPromises()

    expect(wrapper.text()).not.toContain('Создать контакт')
    wrapper.unmount()
  })

  it('applies search filter on submit', async () => {
    const wrapper = mountContactsPage('admin')
    await flushPromises()

    const input = wrapper.find('input[placeholder*="Поиск"]')
    await input.setValue('Иван')
    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(listContactsMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: 'Иван' }),
    )
    wrapper.unmount()
  })
})
