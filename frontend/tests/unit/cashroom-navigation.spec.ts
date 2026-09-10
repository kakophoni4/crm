import { expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { NMenu } from 'naive-ui'
import AppSidebar from '@/widgets/app-layout/AppSidebar.vue'

const { push, auth } = vi.hoisted(() => ({
  push: vi.fn(),
  auth: { isAdmin: true, isKesher: false, isAccountant: false, isLawyer: false,
    user: { permissions: ['cashroom.manage'], group_ids: [] } },
}))
vi.mock('vue-router', () => ({useRouter: () => ({push}), useRoute: () => ({name:'cashroom'})}))
vi.mock('@/shared/store/auth', () => ({useAuthStore: () => auth}))

it.each([false, true])('opens cashroom from the menu and highlights it (kesher=%s)', (kesher) => {
  auth.isKesher = kesher
  auth.isAdmin = !kesher
  push.mockClear()
  const wrapper = mount(AppSidebar, {props:{collapsed:false,mobile:false,drawerVisible:false},global:{stubs:{NLayoutSider:{template:'<div><slot /></div>'}}}})
  const menu = wrapper.findComponent(NMenu)
  expect(menu.props('value')).toBe('cashroom')
  expect(menu.props('options').some(option => option.key === 'cashroom')).toBe(true)
  menu.vm.$emit('update:value', 'cashroom')
  expect(push).toHaveBeenCalledWith({name:'cashroom'})
  expect(wrapper.emitted('closeDrawer')).toHaveLength(1)
  wrapper.unmount()
})
