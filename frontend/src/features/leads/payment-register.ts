import type { OptPaymentRegisterItem, OptPaymentRegisterLine } from './opt-types'

export function groupPaymentShops(order: OptPaymentRegisterItem) {
  const groups = new Map<string, OptPaymentRegisterLine[]>()
  for (const line of order.lines) {
    const key = line.supplier_inn || String(line.id)
    groups.set(key, [...(groups.get(key) ?? []), line])
  }
  return [...groups.entries()].map(([inn, lines]) => {
    const sum = (field: 'volume' | 'due_amount' | 'beneficiary_amount' | 'beneficiary_paid_amount') =>
      lines.reduce((total, line) => total + Number(line[field] || 0), 0)
    const rates = new Set(lines.map((line) => line.beneficiary_rate_percent == null ? null : Number(line.beneficiary_rate_percent)))
    return {
      inn, name: lines[0]?.supplier_name || `Лавка с ИНН ${inn}`, lines,
      volume: sum('volume'), due: sum('due_amount'), beneficiary: sum('beneficiary_amount'),
      returned: sum('beneficiary_paid_amount'),
      configured: lines.every((line) => line.beneficiary_rate_percent != null),
      mixedRates: rates.size > 1,
      rate: rates.size === 1 ? [...rates][0] ?? null : null,
      comment: [...new Set(lines.map((line) => line.comment).filter(Boolean))].join('\n'),
    }
  })
}
