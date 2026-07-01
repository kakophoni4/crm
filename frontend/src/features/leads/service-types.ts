/** Fixed service types for lead orders. Extend when new types are ready. */
export const FIXED_SERVICE_TYPES = [
  { label: 'Деревья', value: 'Деревья' },
  { label: 'ОПТ', value: 'ОПТ' },
] as const

export type FixedServiceType = (typeof FIXED_SERVICE_TYPES)[number]['value']

export function isFixedServiceType(value: string): value is FixedServiceType {
  return FIXED_SERVICE_TYPES.some((row) => row.value === value)
}

/** Service options for a chat's bot; keeps current value if already set on the deal. */
export function serviceOptionsForBot(
  botServiceTypes: string[] | null | undefined,
  currentService?: string,
): Array<{ label: string; value: string }> {
  const allowed =
    botServiceTypes?.length
      ? FIXED_SERVICE_TYPES.filter((row) => botServiceTypes.includes(row.value))
      : [...FIXED_SERVICE_TYPES]
  const options = allowed.map((row) => ({ label: row.label, value: row.value }))
  if (
    currentService &&
    currentService.trim() &&
    !options.some((row) => row.value === currentService)
  ) {
    options.push({ label: currentService, value: currentService })
  }
  return options
}
