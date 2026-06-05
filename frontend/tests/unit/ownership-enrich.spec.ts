import { describe, expect, it } from 'vitest'

import type { ChatListItem } from '@/entities/chat/types'
import type { GroupOwnershipItem } from '@/entities/contact/types'
import { applyOwnershipToChat } from '@/features/chats/ownership-enrich'

const baseChat: ChatListItem = {
  id: 1,
  contact_id: 10,
  contact_name: 'Клиент',
  bot_id: null,
  assigned_user_id: null,
  assigned_group_id: 3,
  assigned_department_id: null,
  status: 'open',
  status_id: null,
  last_message_at: null,
  last_message_preview: null,
  unread_for_me: false,
  card_owner_user_id: 5,
  card_owner_full_name: 'Иван Оператор',
}

describe('applyOwnershipToChat', () => {
  it('keeps API owner name when cache has same id without name', () => {
    const ownership: GroupOwnershipItem = {
      group_id: 3,
      group_name: 'Группа',
      owner_user_id: 5,
      owner_full_name: null,
      pending_inbound_at: null,
      escalated_at: null,
    }
    const result = applyOwnershipToChat(baseChat, ownership)
    expect(result.card_owner_user_id).toBe(5)
    expect(result.card_owner_full_name).toBe('Иван Оператор')
  })

  it('uses cached name when provided after transfer', () => {
    const ownership: GroupOwnershipItem = {
      group_id: 3,
      group_name: 'Группа',
      owner_user_id: 8,
      owner_full_name: 'Борис Тестов',
      pending_inbound_at: null,
      escalated_at: null,
    }
    const result = applyOwnershipToChat(baseChat, ownership)
    expect(result.card_owner_user_id).toBe(8)
    expect(result.card_owner_full_name).toBe('Борис Тестов')
  })

  it('does not keep old name when owner id changed without new name', () => {
    const ownership: GroupOwnershipItem = {
      group_id: 3,
      group_name: 'Группа',
      owner_user_id: 8,
      owner_full_name: null,
      pending_inbound_at: null,
      escalated_at: null,
    }
    const result = applyOwnershipToChat(baseChat, ownership)
    expect(result.card_owner_user_id).toBe(8)
    expect(result.card_owner_full_name).toBeNull()
  })
})
