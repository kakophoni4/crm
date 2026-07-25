import type { RouteRecordRaw } from 'vue-router'

import { createRouter, createWebHistory } from 'vue-router'



import AppLayout from '@/widgets/app-layout/AppLayout.vue'

import { requiresAdminMeta } from '@/shared/lib/admin-routes'

import { useAuthStore } from '@/shared/store/auth'



/** Sync check for guards/tests — call `ensureSession()` in navigation for refresh flow. */

export function requireAuth(): boolean {

  return useAuthStore().isAuthenticated

}



/** Sync admin check for unit tests (store must be hydrated). */

export function requireAdmin(): boolean {

  return useAuthStore().isAdmin

}



const routes: RouteRecordRaw[] = [

  {

    path: '/',

    redirect: () => {
      const auth = useAuthStore()
      if (auth.isAccountant) return '/accounting'
      return '/chats'
    },

  },

  {

    path: '/login',

    name: 'login',

    component: () => import('@/pages/login/index.vue'),

    meta: { layout: false, public: true },

  },

  {

    path: '/share',

    name: 'public-share-upload',

    component: () => import('@/pages/share/upload.vue'),

    meta: { layout: false, public: true },

  },

  {

    path: '/share/:token',

    name: 'public-share-download',

    component: () => import('@/pages/share/download.vue'),

    meta: { layout: false, public: true },

  },

  {

    path: '/',

    component: AppLayout,

    meta: { requiresAuth: true },

    children: [

      {

        path: 'dashboard',

        name: 'dashboard',

        component: () => import('@/pages/dashboard/index.vue'),

      },

      {

        path: 'chats',

        name: 'chats',

        component: () => import('@/pages/chats/index.vue'),

      },

      {

        path: 'contacts',

        name: 'contacts',

        component: () => import('@/pages/contacts/index.vue'),

      },

      {

        path: 'storage',

        name: 'storage',

        component: () => import('@/pages/storage/index.vue'),

      },

      {

        path: 'tasks',

        name: 'tasks',

        component: () => import('@/pages/tasks/index.vue'),

      },

      {

        path: 'applications',

        name: 'applications',

        component: () => import('@/pages/applications/index.vue'),

      },

      {

        path: 'accounting',

        name: 'accounting',

        component: () => import('@/pages/accounting/index.vue'),

        meta: { requiresAccounting: true },

      },

      {

        path: 'telephony',

        name: 'telephony',

        component: () => import('@/pages/telephony/index.vue'),

        meta: { requiresTelephonyCall: true },

      },

      {

        path: 'contacts/:id',

        name: 'contact-detail',

        component: () => import('@/pages/contacts/[id].vue'),

        props: (route) => ({ id: Number(route.params.id) }),

      },

      {

        path: 'settings/group-escalation',

        name: 'group-escalation',

        component: () => import('@/pages/settings/group-escalation.vue'),

        meta: { requiresSenior: true },

      },

      {

        path: 'settings/group-after-hours',

        name: 'group-after-hours',

        component: () => import('@/pages/settings/group-after-hours.vue'),

        meta: { requiresSeniorOrAdmin: true },

      },

      {

        path: 'settings/notifications',

        name: 'notifications',

        component: () => import('@/pages/settings/notifications.vue'),

      },

      {

        path: 'settings/notification-history',

        name: 'notification-history',

        component: () => import('@/pages/settings/notification-history.vue'),

      },

      {

        path: 'settings/statuses',

        name: 'admin-statuses',

        component: () => import('@/pages/admin/statuses.vue'),

        meta: { requiresSeniorOrAdmin: true },

      },

      {

        path: 'admin/statuses',

        redirect: { name: 'admin-statuses' },

      },

      {

        path: 'settings/users',

        name: 'settings-users',

        component: () => import('@/pages/admin/users.vue'),

        meta: { requiresSeniorOrAdmin: true },

      },

      {

        path: 'settings/groups',

        name: 'settings-groups',

        component: () => import('@/pages/admin/groups.vue'),

        meta: { requiresSeniorOrAdmin: true },

      },

      {

        path: 'settings/bots',

        name: 'settings-bots',

        component: () => import('@/pages/settings/bots.vue'),

        meta: { requiresSeniorOrAdmin: true },

      },

      {

        path: 'settings/telephony',

        name: 'settings-telephony',

        component: () => import('@/pages/settings/telephony.vue'),

        meta: { requiresSeniorOrAdmin: true },

      },

      {

        path: 'admin',

        meta: { requiresAdmin: true },

        children: [

          {

            path: '',

            name: 'admin',

            component: () => import('@/pages/admin/index.vue'),

          },

          {

            path: 'departments',

            name: 'admin-departments',

            component: () => import('@/pages/admin/departments.vue'),

          },

          {

            path: 'groups',

            name: 'admin-groups',

            component: () => import('@/pages/admin/groups.vue'),

          },

          {

            path: 'users',

            name: 'admin-users',

            component: () => import('@/pages/admin/users.vue'),

          },

          {

            path: 'bots',

            name: 'admin-bots',

            component: () => import('@/pages/admin/bots.vue'),

          },

          {

            path: 'notification-bot',

            name: 'admin-notification-bot',

            component: () => import('@/pages/admin/notification-bot.vue'),

          },

        ],

      },

    ],

  },

  {

    path: '/:catchAll(.*)',

    component: AppLayout,

    children: [

      {

        path: '',

        name: 'not-found',

        component: () => import('@/pages/not-found/index.vue'),

      },

    ],

  },

]



export const router = createRouter({

  history: createWebHistory(import.meta.env.BASE_URL),

  routes,

})



router.beforeEach(async (to) => {
  if (to.meta.public) {
    if (to.name === 'login') {
      const auth = useAuthStore()
      await auth.hydrate()
      if (auth.isAuthenticated) {
        const defaultRedirect = auth.isAccountant ? '/accounting' : '/chats'
        const redirect = typeof to.query.redirect === 'string' ? to.query.redirect : defaultRedirect
        return redirect
      }
    }
    return true
  }

  const auth = useAuthStore()
  await auth.ensureSession()

  const needsAuth =
    to.matched.some((r) => r.meta.requiresAuth) ||
    to.matched.some((r) => r.meta.requiresSeniorOrAdmin) ||
    to.matched.some((r) => r.meta.requiresAccounting) ||
    to.matched.some((r) => r.meta.requiresTelephonyCall) ||
    requiresAdminMeta(to.meta) ||
    to.matched.some((record) => requiresAdminMeta(record.meta))

  if (needsAuth && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  const needsSeniorOrAdmin = to.matched.some((r) => r.meta.requiresSeniorOrAdmin)
  if (needsSeniorOrAdmin) {
    const role = auth.user?.role
    if (role !== 'admin' && role !== 'senior') return { name: 'contacts' }
  }

  const needsAccounting = to.matched.some((r) => r.meta.requiresAccounting)
  if (needsAccounting && !auth.canAccounting) {
    return { name: 'contacts' }
  }

  if (auth.isAccountant && !needsAccounting) {
    return { name: 'accounting' }
  }

  const needsTelephonyCall = to.matched.some((r) => r.meta.requiresTelephonyCall)
  if (needsTelephonyCall && !auth.user?.permissions.includes('telephony.call')) {
    return { name: 'contacts' }
  }

  const needsAdmin =
    requiresAdminMeta(to.meta) || to.matched.some((record) => requiresAdminMeta(record.meta))
  if (needsAdmin && !auth.isAdmin) {
    return { name: 'contacts' }
  }

  return true
})


