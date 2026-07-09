/** Normalize Russian mobile to E.164 +7XXXXXXXXXX. */
export function normalizeRussianPhone(value: string): string | null {
  const digits = value.replace(/\D/g, '')
  if (digits.length === 10) return `+7${digits}`
  if (digits.length === 11 && (digits.startsWith('7') || digits.startsWith('8'))) {
    return `+7${digits.slice(1)}`
  }
  return null
}
