import { describe, expect, it } from 'vitest'



import {

  chatListItemIsAnswered,
  chatListItemNeedsResponse,
  chatListItemStatusLabel,

  currentLeadIsOpen,

  filterChatWorkflowStatuses,
  filterClientLabelStatuses,
  filterLeadPipelineStatuses,
  filterOpenLeadPipelineStatuses,

  formatCrmSummaryBadge,

  formatLeadBotLabel,

  formatLeadOpenState,

  isChatLabelStatus,

} from '@/features/leads/mapping'

import type { LeadListItem, StatusOption } from '@/features/leads/types'



function status(

  code: string,

  label: string,

  kind?: StatusOption['kind'],

): StatusOption {

  return {

    id: code.length,

    code,

    kind,

    label,

    color: null,

    sort_order: 0,

    is_active: true,

  }

}



describe('leads mapping', () => {

  it('formats crm summary badge when prior leads exist', () => {

    const text = formatCrmSummaryBadge({

      prior_leads_count: 2,

      first_registered_at: '2026-01-15T10:00:00Z',

    })

    expect(text).toBe('Были сделки: 2 · с 15.01.2026')

  })



  it('hides crm badge when no prior leads', () => {

    expect(

      formatCrmSummaryBadge({

        prior_leads_count: 0,

        first_registered_at: '2026-01-15T10:00:00Z',

      }),

    ).toBeNull()

  })



  it('splits statuses by kind when present', () => {

    const items = [

      status('client_new', 'Новый клиент', 'chat_label'),

      status('waiting', 'Ожидает ответа', 'chat_label'),

      status('new', 'Новый', 'lead_pipeline'),

      status('client_returning', 'Постоянный', 'chat_label'),

      status('won', 'Выигран', 'lead_pipeline'),

    ]

    expect(filterChatWorkflowStatuses(items).map((row) => row.code)).toEqual(['waiting'])

    expect(filterClientLabelStatuses(items).map((row) => row.code)).toEqual([
      'client_new',
      'client_returning',
    ])

    expect(filterLeadPipelineStatuses(items).map((row) => row.code)).toEqual(['new', 'won'])

  })



  it('falls back to code lists when kind is missing', () => {

    const items = [

      status('client_new', 'Новый клиент'),

      status('waiting', 'Ожидает ответа'),

      status('answered', 'Отвечен'),

      status('qualified', 'Квалифицирован'),

      status('client_returning', 'Постоянный'),

      status('won', 'Выигран'),

    ]

    expect(filterChatWorkflowStatuses(items).map((row) => row.code)).toEqual([
      'waiting',
      'answered',
    ])

    expect(filterClientLabelStatuses(items).map((row) => row.code)).toEqual([
      'client_new',
      'client_returning',
    ])

    expect(filterLeadPipelineStatuses(items).map((row) => row.code)).toEqual(['won'])

    expect(isChatLabelStatus('client_new')).toBe(true)

  })



  it('chat list status shows workflow label, not lead pipeline', () => {
    expect(
      chatListItemStatusLabel({
        id: 1,
        contact_id: 1,
        contact_name: 'Test',
        bot_id: null,
        assigned_user_id: null,
        assigned_group_id: null,
        assigned_department_id: null,
        status: 'in_progress',
        status_id: null,
        last_message_at: null,
        last_message_preview: null,
        chat_label: { status_id: 1, code: 'waiting', label: 'Ожидает ответа' },
        current_lead: {
          id: 10,
          status_id: 2,
          label: 'Уточняем детали',
          closed_at: null,
        },
      }),
    ).toBe('Ожидает ответа')
  })

  it('answered chats never need inbox stripe even with stale needs_reply', () => {
    const answered = {
      id: 1,
      contact_id: 1,
      contact_name: 'Test',
      bot_id: null,
      assigned_user_id: null,
      assigned_group_id: null,
      assigned_department_id: null,
      status: 'in_progress',
      status_id: null,
      last_message_at: null,
      last_message_preview: null,
      chat_label: { status_id: 2, code: 'answered', label: 'Отвечен' },
      needs_reply: true,
      needs_response: true,
    } as const

    expect(chatListItemIsAnswered(answered)).toBe(true)
    expect(chatListItemNeedsResponse(answered)).toBe(false)
  })

  it('formats lead bot label from API fields', () => {

    const lead = {

      id: 1,

      bot_id: 5,

      bot_name: 'Shop Bot',

      bot_code: 'shop',

    } as LeadListItem

    expect(formatLeadBotLabel(lead)).toBe('Shop Bot (shop)')

    expect(formatLeadBotLabel({ ...lead, bot_name: null, bot_code: 'shop' })).toBe('shop')

    expect(formatLeadBotLabel({ ...lead, bot_name: null, bot_code: null })).toBe('#5')

  })



  it('filters open pipeline without terminal or legacy duplicates', () => {
    const items = [
      status('new', 'Новый', 'lead_pipeline'),
      status('in_progress', 'В работе', 'lead_pipeline'),
      status('won', 'Выигран', 'lead_pipeline'),
      status('lead_new', 'Новый лид', 'lead_pipeline'),
      status('lead_won', 'Выигран легаси', 'lead_pipeline'),
    ]
    const open = filterOpenLeadPipelineStatuses(items)
    expect(open.map((row) => row.code)).toEqual(['new', 'in_progress'])
  })

  it('includes custom open stages after defaults', () => {
    const items = [
      status('new', 'Новый', 'lead_pipeline'),
      status('in_progress', 'В работе', 'lead_pipeline'),
      status('negotiation', 'Переговоры', 'lead_pipeline'),
      status('won', 'Выигран', 'lead_pipeline'),
    ]
    const open = filterOpenLeadPipelineStatuses(items)
    expect(open.map((row) => row.code)).toEqual(['new', 'in_progress', 'negotiation'])
  })

  it('formats lead open state and current lead snippet', () => {

    expect(formatLeadOpenState(null)).toBe('Открыт')

    expect(formatLeadOpenState('2026-05-17T12:00:00Z')).toBe('Закрыт')

    expect(

      currentLeadIsOpen({

        id: 1,

        status_id: 2,

        label: 'В работе',

        closed_at: null,

      }),

    ).toBe(true)

  })

})


