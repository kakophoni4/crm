import { useWindowSize } from '@vueuse/core'
import { computed, type ComputedRef } from 'vue'

import { useAuthStore } from '@/shared/store/auth'

export const PHONE_MAX_WIDTH = 768

const PHONE_CHATS_ALLOWED_ROUTES = new Set([
  'login',
  'chats',
  'public-share-upload',
  'public-share-download',
])

export function isPhoneViewport(width?: number): boolean {
  const resolved =
    width ?? (typeof window === 'undefined' ? PHONE_MAX_WIDTH + 1 : window.innerWidth)
  return resolved <= PHONE_MAX_WIDTH
}

export function isPhoneChatsOnlyRole(auth: { isAccountant: boolean; isLawyer: boolean }): boolean {
  return !auth.isAccountant && !auth.isLawyer
}

export function isPhoneChatsOnly(
  auth: { isAccountant: boolean; isLawyer: boolean },
  width?: number,
): boolean {
  return isPhoneViewport(width) && isPhoneChatsOnlyRole(auth)
}

export function isPhoneChatsAllowedRoute(name: unknown): boolean {
  return typeof name === 'string' && PHONE_CHATS_ALLOWED_ROUTES.has(name)
}

export function usePhoneViewport(): ComputedRef<boolean> {
  const { width } = useWindowSize()
  return computed(() => isPhoneViewport(width.value))
}

export function usePhoneChatsOnly(): ComputedRef<boolean> {
  const { width } = useWindowSize()
  const auth = useAuthStore()
  return computed(() => isPhoneChatsOnly(auth, width.value))
}
