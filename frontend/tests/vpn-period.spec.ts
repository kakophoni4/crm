import { describe, expect, it } from 'vitest'
import { periodEnd, validPeriod, vpnDeliveryText } from '../src/features/vpn/period'

describe('VPN subscription periods', () => {
  it('adds days to active expiry and starts expired renewals from now', () => {
    for (const days of [1, 3, 7, 14, 21]) {
      expect(periodEnd(days, 2000, 1000)).toBe(2000 + days * 86400)
      expect(periodEnd(days, 500, 1000)).toBe(1000 + days * 86400)
    }
  })
  it('requires whole positive days within the API limit', () => {
    for (const value of [null, undefined, 0, -1, 1.5, 3651, NaN]) expect(validPeriod(value)).toBe(false)
    expect(validPeriod(1)).toBe(true)
    expect(validPeriod(3650)).toBe(true)
  })
  it('clearly identifies trial delivery and includes download instructions', () => {
    const text = vpnDeliveryText({ kind: 'trial', expires_at: 2000, happ_url: 'happ-example', ghostlane_url: 'ghostlane-example', clash_url: 'clash-example', v2rayng_url: 'v2ray-example', guide_url: 'guide-example' })
    expect(text).toContain('пробный VPN')
    expect(text).toContain('guide-example')
    expect(text).toContain('happ-example')
    expect(text).toContain('Ghostlane: ghostlane-example')
    expect(text).not.toContain('в подарок')
  })
})
