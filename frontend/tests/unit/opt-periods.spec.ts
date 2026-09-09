import { expect, it } from 'vitest'
import { OPT_PERIOD_OPTIONS, formatOptPeriodLabel } from '@/features/leads/order-fields'

it('offers selling quarters from Q3 2023 through Q4 2026 in order', () => {
  expect(OPT_PERIOD_OPTIONS.map(option => option.value)).toEqual([
    '3/23', '4/23', '1/24', '2/24', '3/24', '4/24',
    '1/25', '2/25', '3/25', '4/25', '1/26', '2/26', '3/26', '4/26',
  ])
  expect(formatOptPeriodLabel('3/23')).toBe('3 кв. 2023')
  expect(formatOptPeriodLabel('4/24')).toBe('4 кв. 2024')
})
