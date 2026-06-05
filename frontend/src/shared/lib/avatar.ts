const AVATAR_PALETTE = [
  '#5B8DEF',
  '#6BCB77',
  '#F4A261',
  '#E76F51',
  '#9B5DE5',
  '#00BBF9',
  '#F15BB5',
  '#2EC4B6',
] as const

/** Initials from full name (up to 2 letters). */
export function getContactInitials(fullName: string): string {
  const parts = fullName
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  if (!parts.length) return '?'
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase()
  }
  return `${parts[0][0] ?? ''}${parts[parts.length - 1][0] ?? ''}`.toUpperCase()
}

function hashId(id: number | string): number {
  const str = String(id)
  let hash = 0
  for (let i = 0; i < str.length; i += 1) {
    hash = (hash << 5) - hash + str.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash)
}

/** Stable accent color from contact or entity id. */
export function avatarColorFromId(id: number | string): string {
  const index = hashId(id) % AVATAR_PALETTE.length
  return AVATAR_PALETTE[index]
}
