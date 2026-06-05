import { mount } from '@vue/test-utils'
import { NConfigProvider } from 'naive-ui'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'

import TakeoverBadge from '@/widgets/chat/TakeoverBadge.vue'
import { useAuthStore } from '@/shared/store/auth'

vi.mock('@/features/chats/api', () => ({
  releaseTakeover: vi.fn(),
}))

function mountBadge(opts: { role: 'user' | 'senior'; seniorId: number }) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().$patch({
    user: {
      id: opts.role === 'senior' ? opts.seniorId : 3,
      email: 'u@crm.local',
      full_name: 'U',
      role: opts.role,
      department_id: 1,
      group_id: null,
      presence: 'online',
      permissions: [],
    },
  })

  const Host = defineComponent({
    setup() {
      return () =>
        h(NConfigProvider, null, () =>
          h(TakeoverBadge, {
            chatId: 1,
            takeover: { chat_id: 1, senior_user_id: opts.seniorId },
          }),
        )
    },
  })

  return mount(Host, { global: { plugins: [pinia] } })
}

describe('TakeoverBadge', () => {
  it('shows manager banner for operator', () => {
    const wrapper = mountBadge({ role: 'user', seniorId: 9 })
    expect(wrapper.text()).toContain('руководитель')
    expect(wrapper.text()).toContain('9')
    wrapper.unmount()
  })

  it('shows release button for takeover senior', () => {
    const wrapper = mountBadge({ role: 'senior', seniorId: 9 })
    expect(wrapper.text()).toContain('Вы подключены')
    expect(wrapper.text()).toContain('Отключиться')
    wrapper.unmount()
  })
})
