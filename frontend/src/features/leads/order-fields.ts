import type { TreeOrderLine, TreePayment } from './tree-service-types'

export interface LeadOrderFields {
  service?: string
  /** OPT period code, e.g. "2/26" = Q2 2026. */
  period?: string | null
  quantity?: number | string | null
  cost?: number | string | null
  cost_price?: number | string | null
  /** Lines for service «Деревья» (multi-type qty/cost). */
  tree_lines?: TreeOrderLine[] | null
  /** Payments recorded on «Деревья» deals. */
  tree_payments?: TreePayment[] | null
  amount_paid?: number | string | null
}

/** Quarter/year options for OPT deals (2025–2026). */
export const OPT_PERIOD_OPTIONS = [2025, 2026].flatMap((year) =>
  [1, 2, 3, 4].map((quarter) => {
    const yy = String(year % 100).padStart(2, '0')
    const value = `${quarter}/${yy}`
    return { label: `${quarter} кв. ${year} (${value})`, value }
  }),
)

/** Human label for period code `2/26` → `2 кв. 2026`. */
export function formatOptPeriodLabel(code: string | null | undefined): string {
  if (!code) return '—'
  const match = OPT_PERIOD_OPTIONS.find((row) => row.value === code)
  if (match) return match.label.replace(/\s*\([^)]*\)\s*$/, '')
  const m = /^([1-4])\/(\d{2})$/.exec(code.trim())
  if (!m) return code
  return `${m[1]} кв. 20${m[2]}`
}

/** Sort key for `2/26` — year then quarter (for newest-first: compare descending). */
export function optPeriodSortKey(code: string | null | undefined): [number, number] {
  const m = /^([1-4])\/(\d{2})$/.exec((code || '').trim())
  if (!m) return [0, 0]
  return [2000 + Number(m[2]), Number(m[1])]
}

export function compareOptPeriodsDesc(a: string, b: string): number {
  const [ay, aq] = optPeriodSortKey(a)
  const [by, bq] = optPeriodSortKey(b)
  if (ay !== by) return by - ay
  return bq - aq
}

export interface LeadDealCustomFields {
  order?: LeadOrderFields | null
  service_suggestions?: string[]
}

function parseTreeLines(raw: unknown): TreeOrderLine[] {
  if (!Array.isArray(raw)) return []
  const out: TreeOrderLine[] = []
  for (const row of raw) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) continue
    const type = String((row as TreeOrderLine).type || '').trim()
    if (!type) continue
    const quantity = (row as TreeOrderLine).quantity
    const cost = (row as TreeOrderLine).cost
    out.push({
      type,
      quantity:
        quantity == null || quantity === ('' as unknown) ? null : Number(quantity),
      cost: cost == null || cost === ('' as unknown) ? null : Number(cost),
    })
  }
  return out
}

export function summarizeTreeLines(lines: TreeOrderLine[]): {
  quantity: number | null
  cost: number | null
} {
  let qtySum = 0
  let costSum = 0
  let hasQty = false
  let hasCost = false
  for (const line of lines) {
    if (line.quantity != null && !Number.isNaN(Number(line.quantity))) {
      qtySum += Number(line.quantity)
      hasQty = true
    }
    if (line.cost != null && !Number.isNaN(Number(line.cost))) {
      costSum += Number(line.cost)
      hasCost = true
    }
  }
  return {
    quantity: hasQty ? qtySum : null,
    cost: hasCost ? costSum : null,
  }
}

function parseTreePayments(raw: unknown): TreePayment[] {
  if (!Array.isArray(raw)) return []
  const out: TreePayment[] = []
  for (const row of raw) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) continue
    const item = row as Partial<TreePayment>
    const amount = Number(item.amount)
    if (!item.id || !Number.isFinite(amount) || amount <= 0 || !item.paid_at) continue
    out.push({
      id: String(item.id),
      amount,
      paid_at: String(item.paid_at),
      payment_type: (item.payment_type as TreePayment['payment_type']) || 'wire',
      recipient: (item.recipient as TreePayment['recipient']) || 'orange',
    })
  }
  return out
}

export function summarizeTreePayments(payments: TreePayment[]): number {
  return payments.reduce((sum, row) => sum + Number(row.amount || 0), 0)
}

export function treePaymentStatus(
  cost: number | null | undefined,
  paid: number,
): 'unpaid' | 'partial' | 'paid' {
  const due = Number(cost || 0)
  if (due <= 0) return paid > 0 ? 'paid' : 'unpaid'
  if (paid <= 0) return 'unpaid'
  if (paid + 0.001 >= due) return 'paid'
  return 'partial'
}

export function readLeadDealFields(
  customFields: Record<string, unknown> | null | undefined,
): LeadDealCustomFields {
  if (!customFields || typeof customFields !== 'object') {
    return {}
  }
  const orderRaw = customFields.order
  if (!orderRaw || typeof orderRaw !== 'object' || Array.isArray(orderRaw)) {
    const suggestions = customFields.service_suggestions
    return {
      order: null,
      service_suggestions: Array.isArray(suggestions)
        ? suggestions.filter((v): v is string => typeof v === 'string')
        : [],
    }
  }
  const base = orderRaw as LeadOrderFields
  const tree_lines = parseTreeLines(base.tree_lines)
  const tree_payments = parseTreePayments(base.tree_payments)
  const order: LeadOrderFields = {
    ...base,
    tree_lines: tree_lines.length ? tree_lines : base.tree_lines ?? null,
    tree_payments: tree_payments.length ? tree_payments : base.tree_payments ?? null,
    amount_paid: tree_payments.length
      ? summarizeTreePayments(tree_payments)
      : base.amount_paid ?? null,
  }
  const suggestions = customFields.service_suggestions
  return {
    order,
    service_suggestions: Array.isArray(suggestions)
      ? suggestions.filter((v): v is string => typeof v === 'string')
      : [],
  }
}

export function buildLeadDealPatch(
  current: Record<string, unknown> | null | undefined,
  patch: LeadDealCustomFields,
): Record<string, unknown> {
  const base = { ...(current ?? {}) }
  delete base.deal_number
  if (patch.order !== undefined) {
    if (patch.order == null) {
      delete base.order
    } else {
      base.order = patch.order
    }
  }
  if (patch.service_suggestions !== undefined) {
    base.service_suggestions = patch.service_suggestions
  }
  return base
}

export function mergeServiceSuggestion(
  current: Record<string, unknown> | null | undefined,
  service: string,
): Record<string, unknown> {
  const trimmed = service.trim()
  if (!trimmed) return { ...(current ?? {}) }
  return buildLeadDealPatch(current, {
    order: { service: trimmed },
  })
}
