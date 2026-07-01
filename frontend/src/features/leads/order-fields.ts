export interface LeadOrderFields {
  service?: string
  quantity?: number | string | null
  cost?: number | string | null
  cost_price?: number | string | null
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
