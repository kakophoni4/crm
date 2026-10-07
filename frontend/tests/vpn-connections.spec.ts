import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import DeviceLimitEditor from '@/features/vpn/VpnDeviceLimitEditor.vue'
import ContactVpnPanel from '@/widgets/chat/ContactVpnPanel.vue'

const mocks = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn(), success: vi.fn(), error: vi.fn() }))
vi.mock('@/shared/api/http', () => ({ http: { post: mocks.post, get: mocks.get } }))
vi.mock('@/shared/store/auth', () => ({ useAuthStore: () => ({ user: { permissions: ['contacts.read', 'contacts.update', 'chats.write'] } }) }))
vi.mock('@/shared/lib/phone-mode', async () => ({ usePhoneChatsOnly: () => ({ value: false }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('naive-ui', async () => {
  const { defineComponent, h } = await import('vue')
  const container = defineComponent({ setup: (_, { slots }) => () => h('div', slots.default?.()) })
  return {
    useMessage: () => ({ success: mocks.success, error: mocks.error }), useDialog: () => ({ warning: vi.fn(), info: vi.fn() }),
    NDropdown: container, NCard: container, NAlert: container, NSpin: container, NTag: container, NModal: container,
    NButton: defineComponent({ props: ['disabled', 'loading'], setup: (props, { slots }) => () => h('button', { disabled: props.disabled }, slots.default?.()) }),
    NSelect: defineComponent({ props: ['value', 'options', 'disabled'], emits: ['update:value'], setup: (props, { emit }) => () => h('select', { value: props.value, disabled: props.disabled, onChange: (e: Event) => emit('update:value', Number((e.target as HTMLSelectElement).value)) }, (props.options || []).map((o: { label: string; value: number }) => h('option', { value: o.value }, o.label))) }),
  }
})

const subscription = { id: 'sub-one', status: 'active', kind: 'purchase', device_limit: 3, occupied_slots: 1, connections: [{ ip: '203.0.113.1', nodes: 'pl,fi', connected_at: 2000000000 }], expires_at: 2000000000, enabled: true, upload_bytes: 0, download_bytes: 0, happ_url: 'https://vpn.example.com/sub/test?format=happ', ghostlane_url: 'https://vpn.example.com/sub/test?format=ghostlane', clash_url: 'https://vpn.example.com/sub/test?format=clash', v2rayng_url: 'https://vpn.example.com/sub/test?format=v2rayng', guide_url: 'https://vpn.example.com/sub/test?format=guide' }
function panel(eligibility: { can_create: boolean; trial_available: boolean; trial_used: boolean }, items: unknown[] = []) {
  mocks.get.mockImplementation((url: string) => Promise.resolve({ data: url === '/vpn/subscriptions' ? { items, eligibility } : url.includes('/contacts/') ? { linked_bots: [] } : { items: [] } }))
  return mount(ContactVpnPanel, { props: { contactId: 12, chatId: 42 }, global: { stubs: { TrialVpnDialog: true, VpnPeriodPicker: true } } })
}
describe('VPN issuance and connection controls', () => {
  beforeEach(() => { vi.clearAllMocks() })
  it('hides trial and issuance for an existing subscription and shows slot counts without IP addresses', async () => {
    const wrapper = panel({ can_create: false, trial_available: false, trial_used: false }, [subscription])
    await flushPromises()
    expect(wrapper.text()).not.toContain('Отправить пробный VPN')
    expect(wrapper.findAll('button').some(b => ['Подарить VPN', 'Оформить продажу'].includes(b.text()))).toBe(false)
    expect(wrapper.text()).toContain('Продлить')
    expect(wrapper.text()).toContain('Занято 1 из 3 подключений')
    expect(wrapper.text()).not.toContain('203.0.113.1')
    wrapper.unmount()
  })
  it('offers a first trial but removes it after it has been used', async () => {
    const first = panel({ can_create: true, trial_available: true, trial_used: false })
    await flushPromises(); expect(first.text()).toContain('Отправить пробный VPN'); first.unmount()
    const used = panel({ can_create: true, trial_available: false, trial_used: true })
    await flushPromises(); expect(used.text()).not.toContain('Отправить пробный VPN'); used.unmount()
  })
  it('saves a manager-selected limit with an explicit button and allows only 3 through 8', async () => {
    mocks.post.mockResolvedValue({})
    const wrapper = mount(DeviceLimitEditor, { props: { subscriptionId: 'sub-one', deviceLimit: 3 } })
    expect(wrapper.findAll('option').map(o => o.attributes('value'))).toEqual(['3', '4', '5', '6', '7', '8'])
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
    await wrapper.find('select').setValue('8'); await wrapper.find('button').trigger('click'); await flushPromises()
    expect(mocks.post).toHaveBeenCalledWith('/vpn/subscriptions/sub-one/action', { action: 'set_device_limit', device_limit: 8 })
    expect(wrapper.emitted('saved')).toHaveLength(1); wrapper.unmount()
  })
  it('does not report a completed save for a different contact after switching subscriptions', async () => {
    let resolve!: (value: unknown) => void
    mocks.post.mockReturnValue(new Promise(r => { resolve = r }))
    const wrapper = mount(DeviceLimitEditor, { props: { subscriptionId: 'sub-one', deviceLimit: 3 } })
    await wrapper.find('select').setValue('8'); await wrapper.find('button').trigger('click')
    await wrapper.setProps({ subscriptionId: 'sub-two', deviceLimit: 3 })
    resolve({}); await flushPromises()
    expect(wrapper.emitted('saved')).toBeUndefined(); wrapper.unmount()
  })
})
