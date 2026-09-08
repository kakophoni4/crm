import { describe, expect, it } from 'vitest'
import { groupPaymentShops } from '@/features/leads/payment-register'
import type { OptPaymentRegisterItem, OptPaymentRegisterLine } from '@/features/leads/opt-types'

function line(id: number, inn: string, rate: number | null): OptPaymentRegisterLine {
  return { id, supplier_inn: inn, volume: 100, our_rate_percent: 1, due_amount: 1, paid_amount: 0, remaining_amount: 1, beneficiary_rate_percent: rate, beneficiary_amount: rate ?? 0, actual_margin: 0, planned_margin: 1, beneficiary_paid_amount: 0.5 }
}
describe('payment register shop groups', () => {
  it('groups invoice rows by INN and preserves totals', () => {
    const groups = groupPaymentShops({ lines: [line(1, '111', null), line(2, '111', null), line(3, '222', 0)] } as OptPaymentRegisterItem)
    expect(groups).toHaveLength(2)
    expect(groups[0]).toMatchObject({ volume: 200, due: 2, returned: 1, configured: false, rate: null })
    expect(groups[1]).toMatchObject({ configured: true, rate: 0 })
  })
  it('does not turn missing or mixed beneficiary rates into a fake zero', () => {
    const [group] = groupPaymentShops({ lines: [line(1, '111', 0.5), line(2, '111', 1)] } as OptPaymentRegisterItem)
    expect(group).toMatchObject({ mixedRates: true, rate: null, configured: true })
  })
})
