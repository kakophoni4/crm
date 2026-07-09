import type { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import * as authApi from '@/features/auth/api'
import type { MeResponse } from '@/features/auth/api'
import { AppError, http, parseAppError } from '@/shared/api/http'
import { storage } from '@/shared/lib/storage'
import { connectChatsRealtime } from '@/shared/realtime/chats-ws'
import { connectContactsRealtime } from '@/shared/realtime/contacts-ws'
import { requestNotificationPermission } from '@/shared/lib/browser-notifications'
import { connectOwnershipRealtime } from '@/shared/realtime/ownership-ws'

const ACCESS_KEY = 'crm.auth.access_token'
const REFRESH_KEY = 'crm.auth.refresh_token'

let interceptorsInstalled = false
let refreshPromise: Promise<boolean> | null = null

function persistTokens(access: string | null, refresh: string | null): void {
  if (access) storage.set(ACCESS_KEY, access)
  else storage.remove(ACCESS_KEY)
  if (refresh) storage.set(REFRESH_KEY, refresh)
  else storage.remove(REFRESH_KEY)
}

function loadPersistedTokens(): { access: string | null; refresh: string | null } {
  return {
    access: storage.get(ACCESS_KEY),
    refresh: storage.get(REFRESH_KEY),
  }
}

export function setupAuthHttpInterceptors(): void {
  if (interceptorsInstalled) return
  interceptorsInstalled = true

  http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const store = useAuthStore()
    if (store.accessToken) {
      config.headers = config.headers ?? {}
      config.headers.Authorization = `Bearer ${store.accessToken}`
    }
    return config
  })

  http.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean }
      const url = original?.url ?? ''

      if (url.includes('/auth/login') || url.includes('/auth/refresh')) {
        return Promise.reject(parseAppError(error))
      }

      if (!original || original._retry || error.response?.status !== 401) {
        return Promise.reject(parseAppError(error))
      }

      const store = useAuthStore()
      if (!store.refreshToken) {
        store.clearSession()
        return Promise.reject(parseAppError(error))
      }

      original._retry = true
      const refreshed = await store.tryRefresh()
      if (!refreshed) {
        store.clearSession()
        return Promise.reject(parseAppError(error))
      }

      original.headers = original.headers ?? {}
      original.headers.Authorization = `Bearer ${store.accessToken}`
      return http.request(original)
    },
  )
}

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(null)
  const refreshToken = ref<string | null>(null)
  const user = ref<MeResponse | null>(null)
  const hydrated = ref(false)

  const isAuthenticated = computed(() => !!accessToken.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const isSenior = computed(() => user.value?.role === 'senior')
  const isAccountant = computed(() => user.value?.role === 'accountant')
  const canAccounting = computed(
    () => user.value?.permissions.includes('accounting.read') === true,
  )
  const canViewHistoryActor = computed(
    () => isAdmin.value || isSenior.value,
  )

  function setTokens(access: string, refresh: string): void {
    accessToken.value = access
    refreshToken.value = refresh
    persistTokens(access, refresh)
  }

  function clearSession(): void {
    accessToken.value = null
    refreshToken.value = null
    user.value = null
    persistTokens(null, null)
  }

  async function fetchMe(): Promise<void> {
    user.value = await authApi.me()
  }

  async function login(username: string, password: string): Promise<void> {
    const data = await authApi.login(username, password)
    setTokens(data.access_token, data.refresh_token)
    await fetchMe()
    void connectContactsRealtime()
    void connectChatsRealtime()
    void connectOwnershipRealtime()
    void requestNotificationPermission()
  }

  async function tryRefresh(): Promise<boolean> {
    if (!refreshToken.value) return false
    if (refreshPromise) return refreshPromise

    refreshPromise = (async () => {
      try {
        const data = await authApi.refresh(refreshToken.value!)
        setTokens(data.access_token, data.refresh_token)
        return true
      } catch (err) {
        if (err instanceof AppError && (err.status === 401 || err.status === 403)) {
          return false
        }
        throw err
      } finally {
        refreshPromise = null
      }
    })()

    return refreshPromise
  }

  async function logout(): Promise<void> {
    const token = refreshToken.value
    clearSession()
    if (token) {
      try {
        await authApi.logout(token)
      } catch {
      }
    }
  }

  async function hydrate(): Promise<void> {
    if (hydrated.value) return
    const persisted = loadPersistedTokens()
    refreshToken.value = persisted.refresh
    accessToken.value = persisted.access

    if (!accessToken.value && refreshToken.value) {
      await tryRefresh()
    }

    if (accessToken.value) {
      try {
        await fetchMe()
      } catch {
        if (refreshToken.value) {
          const ok = await tryRefresh()
          if (ok) {
            try {
              await fetchMe()
            } catch {
              clearSession()
            }
          } else {
            clearSession()
          }
        } else {
          clearSession()
        }
      }
    }

    if (isAuthenticated.value) {
      void requestNotificationPermission()
    }

    hydrated.value = true
  }

  async function ensureSession(): Promise<boolean> {
    await hydrate()
    if (isAuthenticated.value) return true
    if (refreshToken.value) {
      const ok = await tryRefresh()
      if (ok) {
        try {
          await fetchMe()
          return true
        } catch {
          clearSession()
        }
      }
    }
    return false
  }

  return {
    accessToken,
    refreshToken,
    user,
    hydrated,
    isAuthenticated,
    isAdmin,
    isSenior,
    isAccountant,
    canAccounting,
    canViewHistoryActor,
    login,
    logout,
    fetchMe,
    tryRefresh,
    clearSession,
    hydrate,
    ensureSession,
  }
})
