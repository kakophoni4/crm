import { format } from 'date-fns'



import type { ChatLabelSnippet, ChatListItem, CurrentLeadSnippet } from '@/entities/chat/types'
import { CHAT_STATUS_OPTIONS } from '@/entities/chat/types'

import { lookupBotCode, lookupBotName } from '@/features/bots/directory'
import type { ContactCrmSummary, LeadListItem, StatusKind, StatusOption } from '@/features/leads/types'



/** Fallback when API rows omit `kind` (backward compat). */

export const CHAT_WORKFLOW_CODES = ['new', 'waiting', 'answered', 'done'] as const

export const CLIENT_LABEL_CODES = ['client_new', 'client_returning'] as const

/** @deprecated use CLIENT_LABEL_CODES */
export const CHAT_LABEL_CODES = CLIENT_LABEL_CODES



export const LEAD_PIPELINE_CODES = ['new', 'in_progress', 'won', 'lost'] as const

export const LEAD_OPEN_PIPELINE_CODES = ['new', 'in_progress'] as const



function resolveStatusKind(row: StatusOption): StatusKind | null {

  if (row.kind === 'chat_label' || row.kind === 'lead_pipeline') return row.kind

  return null

}



export function isChatWorkflowStatus(code: string): boolean {
  return (CHAT_WORKFLOW_CODES as readonly string[]).includes(code)
}

export function isClientLabelStatus(code: string): boolean {
  return (CLIENT_LABEL_CODES as readonly string[]).includes(code)
}

export function isChatLabelStatus(code: string): boolean {
  return isClientLabelStatus(code)
}

export function isLeadPipelineStatus(code: string): boolean {

  return (LEAD_PIPELINE_CODES as readonly string[]).includes(code)

}



function matchesChatWorkflow(row: StatusOption): boolean {
  const kind = resolveStatusKind(row)
  if (kind != null) return kind === 'chat_label' && isChatWorkflowStatus(row.code)
  return isChatWorkflowStatus(row.code)
}

function matchesClientLabel(row: StatusOption): boolean {
  const kind = resolveStatusKind(row)
  if (kind != null) return kind === 'chat_label' && isClientLabelStatus(row.code)
  return isClientLabelStatus(row.code)
}

function matchesLeadPipeline(row: StatusOption): boolean {

  const kind = resolveStatusKind(row)

  if (kind != null) return kind === 'lead_pipeline'

  return isLeadPipelineStatus(row.code)

}



export function filterChatWorkflowStatuses(items: StatusOption[]): StatusOption[] {
  return items
    .filter((row) => row.is_active && matchesChatWorkflow(row))
    .sort((a, b) => a.sort_order - b.sort_order)
}

export function formatContactClientLabel(code: string | null | undefined): string | null {
  if (!code) return null
  const normalized = code.trim().toLowerCase()
  if (normalized === 'new' || normalized === 'client_new') return 'Новый клиент'
  if (normalized === 'returning' || normalized === 'client_returning') return 'Повторный клиент'
  return code
}

export function filterClientLabelStatuses(items: StatusOption[]): StatusOption[] {
  return items
    .filter((row) => row.is_active && matchesClientLabel(row))
    .sort((a, b) => a.sort_order - b.sort_order)
}

/** @deprecated use filterChatWorkflowStatuses */
export function filterChatLabelStatuses(items: StatusOption[]): StatusOption[] {
  return filterChatWorkflowStatuses(items)
}



export const LEAD_TERMINAL_CODES = ['won', 'lost', 'lead_won', 'lead_lost'] as const

export function isLeadTerminalStatus(code: string): boolean {
  return (LEAD_TERMINAL_CODES as readonly string[]).includes(code)
}

export function resolveTerminalStatusId(
  items: StatusOption[],
  codes: readonly string[],
): number | null {
  for (const code of codes) {
    const row = items.find((item) => item.code === code)
    if (row != null) return row.id
  }
  return null
}

export function filterLeadPipelineStatuses(items: StatusOption[]): StatusOption[] {

  return items

    .filter((row) => row.is_active && matchesLeadPipeline(row))

    .sort((a, b) => a.sort_order - b.sort_order)

}

export function filterOpenLeadPipelineStatuses(items: StatusOption[]): StatusOption[] {
  const pipeline = filterLeadPipelineStatuses(items).filter((row) => !isLeadTerminalStatus(row.code))
  const canonical = pipeline.filter((row) =>
    (LEAD_OPEN_PIPELINE_CODES as readonly string[]).includes(row.code),
  )
  const custom = pipeline.filter(
    (row) =>
      !(LEAD_OPEN_PIPELINE_CODES as readonly string[]).includes(row.code) &&
      !row.code.startsWith('lead_'),
  )
  return [...canonical, ...custom]
}



export function formatLeadOpenState(closedAt: string | null): string {

  return closedAt == null ? 'Открыт' : 'Закрыт'

}



export function formatLeadDate(iso: string): string {

  try {

    return format(new Date(iso), 'dd.MM.yyyy HH:mm')

  } catch {

    return iso

  }

}



export function formatBotLabel(item: {
  bot_id?: number | null
  bot_name?: string | null
  bot_code?: string | null
}): string {
  if (item.bot_id == null) return '—'
  const botName = item.bot_name ?? lookupBotName(item.bot_id)
  const botCode = item.bot_code ?? lookupBotCode(item.bot_id)

  if (botName && botCode) return `${botName} (${botCode})`
  if (botName) return botName
  if (botCode) return botCode
  return `#${item.bot_id}`
}



export function formatLeadBotLabel(lead: LeadListItem): string {
  return formatBotLabel(lead)
}



export function formatCrmSummaryBadge(summary: ContactCrmSummary | null | undefined): string | null {

  if (!summary || summary.prior_leads_count <= 0) return null

  let datePart = summary.first_registered_at

  try {

    datePart = format(new Date(summary.first_registered_at), 'dd.MM.yyyy')

  } catch {

    /* keep raw */

  }

  return `Были сделки: ${summary.prior_leads_count} · с ${datePart}`

}



export function leadListItemLabel(lead: LeadListItem): string {

  if (lead.status_label) return lead.status_label

  if (lead.status_code) return lead.status_code

  return '—'

}



export function currentLeadIsOpen(lead: CurrentLeadSnippet | null | undefined): boolean {

  return lead != null && lead.closed_at == null

}

/** Подпись статуса в списке чатов: workflow чата (не воронка сделки). */
export function chatListItemStatusLabel(chat: ChatListItem): string | null {
  const workflow = chat.chat_label?.label?.trim()
  if (workflow) return workflow

  const legacy = CHAT_STATUS_OPTIONS.find((row) => row.value === chat.status)?.label
  return legacy ?? null
}

const CHAT_WORKFLOW_FALLBACK_LABELS: Record<string, string> = {
  new: 'Новый',
  waiting: 'Ожидает ответа',
  answered: 'Отвечен',
  done: 'Завершён',
}

/** Optimistic list patch when realtime event has no full chat_label payload. */
export function chatWorkflowLabelPatch(
  code: 'waiting' | 'answered',
): Pick<ChatListItem, 'chat_label'> {
  return {
    chat_label: {
      status_id: null,
      code,
      label: CHAT_WORKFLOW_FALLBACK_LABELS[code] ?? code,
    },
  }
}



export function chatLabelStatusId(label: ChatLabelSnippet | null | undefined): number | null {

  return label?.status_id ?? null

}


