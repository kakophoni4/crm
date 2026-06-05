import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { storage } from '@/shared/lib/storage'
import { useThemeStore } from '@/shared/store/theme'

describe('theme store', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation((query: string) => ({
        matches: query.includes('dark') ? false : false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    )
    storage.remove('crm-theme-mode')
    document.documentElement.classList.remove('dark')
    const pinia = createPinia()
    setActivePinia(pinia)
  })

  it('persists preference in localStorage', () => {
    const store = useThemeStore()
    store.setPreference('dark')

    expect(storage.get('crm-theme-mode')).toBe('dark')
    expect(store.isDark).toBe(true)
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('resolves system preference to light when OS is light', () => {
    const store = useThemeStore()
    store.setPreference('system')

    expect(store.preference).toBe('system')
    expect(store.isDark).toBe(false)
  })

  it('toggle switches between light and dark', () => {
    const store = useThemeStore()
    store.setPreference('light')
    store.toggle()
    expect(store.isDark).toBe(true)
    store.toggle()
    expect(store.isDark).toBe(false)
  })
})
