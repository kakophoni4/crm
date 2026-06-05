import { describe, expect, it } from 'vitest'

import { avatarColorFromId, getContactInitials } from '@/shared/lib/avatar'

describe('contact avatar utils', () => {
  it('builds initials from full name', () => {
    expect(getContactInitials('Иван Петров')).toBe('ИП')
    expect(getContactInitials('Anna')).toBe('AN')
    expect(getContactInitials('  ')).toBe('?')
  })

  it('returns stable color for the same id', () => {
    const a = avatarColorFromId(42)
    const b = avatarColorFromId(42)
    const c = avatarColorFromId(43)
    expect(a).toBe(b)
    expect(a).not.toBe(c)
  })
})
