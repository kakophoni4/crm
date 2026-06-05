import type { LeadCommentItem, LeadListItem } from '@/features/leads/types'

export function leadCommentItems(lead: LeadListItem): LeadCommentItem[] {
  if (Array.isArray(lead.comments) && lead.comments.length > 0) {
    return lead.comments
  }
  const legacy = lead.comment?.trim()
  if (!legacy) {
    return []
  }
  return [
    {
      id: -lead.id,
      body: legacy,
      created_at: lead.created_at,
    },
  ]
}
