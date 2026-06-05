import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

import { storage } from '@/shared/lib/storage'

const STORAGE_KEY = 'crm-theme-mode'

export type ThemePreference = 'light' | 'dark' | 'system'
export type ResolvedThemeMode = 'light' | 'dark'

function readPersistedPreference(): ThemePreference {
  const raw = storage.get(STORAGE_KEY)
  if (raw === 'light' || raw === 'dark' || raw === 'system') return raw
  return 'system'
}

function resolveMode(preference: ThemePreference): ResolvedThemeMode {
  if (preference === 'light') return 'light'
  if (preference === 'dark') return 'dark'
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark'
  }
  return 'light'
}

export const useThemeStore = defineStore('theme', () => {
  const preference = ref<ThemePreference>(readPersistedPreference())
  const resolvedMode = ref<ResolvedThemeMode>(resolveMode(preference.value))

  const isDark = computed(() => resolvedMode.value === 'dark')

  let mediaQuery: MediaQueryList | null = null

  function applyDomClass(): void {
    document.documentElement.classList.toggle('dark', isDark.value)
  }

  function syncResolvedMode(): void {
    resolvedMode.value = resolveMode(preference.value)
    applyDomClass()
  }

  function setPreference(next: ThemePreference): void {
    preference.value = next
    storage.set(STORAGE_KEY, next)
    syncResolvedMode()
  }

  function cyclePreference(): void {
    const order: ThemePreference[] = ['light', 'dark', 'system']
    const idx = order.indexOf(preference.value)
    setPreference(order[(idx + 1) % order.length])
  }

  function toggle(): void {
    setPreference(isDark.value ? 'light' : 'dark')
  }

  function bindSystemPreferenceListener(): void {
    if (typeof window === 'undefined') return
    mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (): void => {
      if (preference.value === 'system') syncResolvedMode()
    }
    mediaQuery.addEventListener('change', handler)
  }

  watch(isDark, applyDomClass, { immediate: true })
  bindSystemPreferenceListener()

  return {
    preference,
    resolvedMode,
    isDark,
    setPreference,
    cyclePreference,
    toggle,
  }
})
