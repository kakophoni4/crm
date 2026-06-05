import type { UserRole } from '@/features/auth/api'

export function transferHintForRole(role: UserRole | undefined): string {
  if (role === 'user') {
    return 'Запрос уйдёт старшему на согласование.'
  }
  if (role === 'senior' || role === 'admin') {
    return 'Карточка будет сразу назначена выбранному сотруднику в этой группе.'
  }
  return 'Согласие будет получено у получателя.'
}
