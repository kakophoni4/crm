/** Admin SPA routes — shared between router and unit tests. */
export const ADMIN_ROUTE_NAMES = [
  'admin',
  'admin-departments',
  'admin-groups',
  'admin-users',
  'admin-bots',
] as const

export type AdminRouteName = (typeof ADMIN_ROUTE_NAMES)[number]

export function isAdminRouteName(name: string | symbol | null | undefined): boolean {
  if (typeof name !== 'string') return false
  return (ADMIN_ROUTE_NAMES as readonly string[]).includes(name)
}

export function requiresAdminMeta(meta: Record<string, unknown> | undefined): boolean {
  return meta?.requiresAdmin === true
}
