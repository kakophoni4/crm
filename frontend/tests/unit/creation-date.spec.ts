import { describe, expect, it } from 'vitest'
import { formatCreationDate } from '../../src/shared/lib/creation-date'

describe('application creation date', () => {
  it('treats legacy timestamps as UTC and respects explicit offsets', () => {
    const expected = new Intl.DateTimeFormat('ru-RU', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(new Date('2026-10-04T23:30:00Z'))
    expect(formatCreationDate('2026-10-04T23:30:00')).toBe(expected)
    expect(formatCreationDate('2026-10-04 23:30:00.000000')).toBe(expected)
    expect(formatCreationDate('2026-10-05T03:30:00+04:00')).toBe(expected)
  })
  it('handles missing or invalid timestamps', () => {
    expect(formatCreationDate(null)).toBe('—')
    expect(formatCreationDate(undefined)).toBe('—')
    expect(formatCreationDate('invalid')).toBe('—')
  })
})
