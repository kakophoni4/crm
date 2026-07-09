import type { UserRole } from '@/features/auth/api'

export function transferHintForRole(role: UserRole | undefined): string {
  if (role === 'user') {
    return 'Карточка сразу перейдёт выбранному коллеге.'
  }
  if (role === 'senior' || role === 'admin') {
    return 'Карточка будет сразу назначена выбранному сотруднику, в том числе вам.'
  }
  return 'Карточка будет сразу назначена выбранному сотруднику.'
}
