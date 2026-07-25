import type { Contact, ContactStatus } from '@/entities/contact/types'

export interface ContactListPatch {
  contactId: number
  patch: Partial<Contact>
}

function parseContactId(payload: Record<string, unknown>): number | undefined {
  const raw = payload.contact_id
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw
  if (typeof raw === 'string' && raw.trim() !== '') {
    const parsed = Number(raw)
    if (Number.isFinite(parsed)) return parsed
  }
  return undefined
}

/** Best-effort row patch from WS ownership / contact payloads (full reload remains fallback). */
export function extractContactListPatch(
  payload: Record<string, unknown>,
): ContactListPatch | undefined {
  const contactId = parseContactId(payload)
  if (contactId == null) return undefined

  const patch: Partial<Contact> = {}

  if (typeof payload.contact_full_name === 'string') {
    patch.full_name = payload.contact_full_name
  }

  const nested = payload.contact
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    const row = nested as Record<string, unknown>
    if (typeof row.full_name === 'string') patch.full_name = row.full_name
    if (typeof row.note === 'string' || row.note === null) patch.note = row.note as string | null
    if (typeof row.phone === 'string' || row.phone === null) patch.phone = row.phone as string | null
    if (typeof row.email === 'string' || row.email === null) patch.email = row.email as string | null
    if (typeof row.telegram_username === 'string' || row.telegram_username === null) {
      patch.telegram_username = row.telegram_username as string | null
    }
    if (typeof row.status === 'string') patch.status = row.status as ContactStatus
  }

  if (Object.keys(patch).length === 0) return undefined
  return { contactId, patch }
}
