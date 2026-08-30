import { describe, expect, it } from 'vitest'

import {
  isPhoneChatsAllowedRoute,
  isPhoneChatsOnly,
  isPhoneViewport,
  PHONE_MAX_WIDTH,
} from '@/shared/lib/phone-mode'

describe('phone-mode', () => {
  it('treats narrow viewports as phones', () => {
    expect(isPhoneViewport(375)).toBe(true)
    expect(isPhoneViewport(PHONE_MAX_WIDTH)).toBe(true)
    expect(isPhoneViewport(PHONE_MAX_WIDTH + 1)).toBe(false)
  })

  it('locks managers to chats on a phone, but not accountants or lawyers', () => {
    expect(isPhoneChatsOnly({ isAccountant: false, isLawyer: false }, 390)).toBe(true)
    expect(isPhoneChatsOnly({ isAccountant: true, isLawyer: false }, 390)).toBe(false)
    expect(isPhoneChatsOnly({ isAccountant: false, isLawyer: true }, 390)).toBe(false)
    expect(isPhoneChatsOnly({ isAccountant: false, isLawyer: false }, 1280)).toBe(false)
  })

  it('allows only login, chats and public share routes', () => {
    expect(isPhoneChatsAllowedRoute('chats')).toBe(true)
    expect(isPhoneChatsAllowedRoute('login')).toBe(true)
    expect(isPhoneChatsAllowedRoute('contacts')).toBe(false)
    expect(isPhoneChatsAllowedRoute('dashboard')).toBe(false)
  })
})
