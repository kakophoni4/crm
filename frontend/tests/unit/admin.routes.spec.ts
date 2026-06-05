import { beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import { requireAdmin } from '@/app/router'
import {
  ADMIN_ROUTE_NAMES,
  isAdminRouteName,
  requiresAdminMeta,
} from '@/shared/lib/admin-routes'
import { useAuthStore } from '@/shared/store/auth'

function buildRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/contacts', name: 'contacts', component: { template: '<div />' } },
      {
        path: '/settings/statuses',
        name: 'admin-statuses',
        meta: { requiresSeniorOrAdmin: true },
        component: { template: '<div />' },
      },
      {
        path: '/admin',
        meta: { requiresAdmin: true },
        children: [
          { path: '', name: 'admin', component: { template: '<div />' } },
        ],
      },
    ],
  })
}

function seniorOrAdminGuard(to: { matched: { meta: Record<string, unknown> }[] }) {
  const needsSeniorOrAdmin = to.matched.some((r) => r.meta.requiresSeniorOrAdmin)
  if (needsSeniorOrAdmin) {
    const auth = useAuthStore()
    const role = auth.user?.role
    if (role !== 'admin' && role !== 'senior') return { name: 'contacts' }
  }
  const needsAdmin = to.matched.some((r) => requiresAdminMeta(r.meta))
  if (needsAdmin && !requireAdmin()) {
    return { name: 'contacts' }
  }
  return true
}

describe('admin routes', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('maps all admin route names', () => {
    expect(ADMIN_ROUTE_NAMES).toEqual([
      'admin',
      'admin-departments',
      'admin-groups',
      'admin-users',
      'admin-bots',
    ])
    expect(isAdminRouteName('admin-bots')).toBe(true)
    expect(isAdminRouteName('admin-statuses')).toBe(false)
    expect(isAdminRouteName('contacts')).toBe(false)
  })

  it('detects requiresAdmin meta on matched records', () => {
    expect(requiresAdminMeta({ requiresAdmin: true })).toBe(true)
    expect(requiresAdminMeta({})).toBe(false)
  })

  it('redirects regular user away from /settings/statuses', async () => {
    const router = buildRouter()
    router.beforeEach(async (to) => seniorOrAdminGuard(to))

    const auth = useAuthStore()
    auth.user = {
      id: 1,
      email: 'op@example.com',
      full_name: 'Operator',
      role: 'user',
      department_id: 1,
      group_id: 1,
      presence: 'offline',
      permissions: [],
    }
    auth.accessToken = 'test-token'

    await router.push('/settings/statuses')
    expect(router.currentRoute.value.name).toBe('contacts')
  })

  it('allows senior to open statuses', async () => {
    const router = buildRouter()
    router.beforeEach(async (to) => seniorOrAdminGuard(to))

    const auth = useAuthStore()
    auth.user = {
      id: 2,
      email: 'senior@example.com',
      full_name: 'Senior',
      role: 'senior',
      department_id: 1,
      group_id: 1,
      presence: 'offline',
      permissions: [],
    }
    auth.accessToken = 'test-token'

    await router.push('/settings/statuses')
    expect(router.currentRoute.value.name).toBe('admin-statuses')
  })

  it('allows admin to open admin routes', async () => {
    const router = buildRouter()
    router.beforeEach(async (to) => seniorOrAdminGuard(to))

    const auth = useAuthStore()
    auth.user = {
      id: 1,
      email: 'admin@example.com',
      full_name: 'Admin',
      role: 'admin',
      department_id: null,
      group_id: null,
      presence: 'offline',
      permissions: [],
    }
    auth.accessToken = 'test-token'

    await router.push('/admin')
    expect(router.currentRoute.value.name).toBe('admin')
  })
})
