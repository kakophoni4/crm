export interface LeadOrderFields {
  service?: string
  /** OPT period code, e.g. "2/26" = Q2 2026. */
  period?: string | null
  quantity?: number | string | null
  cost?: number | string | null
  cost_price?: number | string | null
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

export interface LeadDealCustomFields {
  order?: LeadOrderFields | null
  service_suggestions?: string[]
}

export function readLeadDealFields(
  customFields: Record<string, unknown> | null | undefined,
): LeadDealCustomFields {
  if (!customFields || typeof customFields !== 'object') {
    return {}
  }
  const orderRaw = customFields.order
  const order =
    orderRaw && typeof orderRaw === 'object' && !Array.isArray(orderRaw)
      ? (orderRaw as LeadOrderFields)
      : null
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
