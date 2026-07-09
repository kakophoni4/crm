import { createPinia, setActivePinia } from 'pinia'

import { beforeEach, describe, expect, it, vi } from 'vitest'



import type { ContactTransferRecord } from '@/entities/contact/types'
import { transferHintForRole } from '@/features/chats/transfer-hint'
import { requestContactTransfer } from '@/features/contacts/api'



vi.mock('@/features/contacts/api', () => ({

  requestContactTransfer: vi.fn(),

}))



const requestContactTransferMock = vi.mocked(requestContactTransfer)



describe('transfer card modal', () => {

  beforeEach(() => {

    requestContactTransferMock.mockReset()

    const transferRecord: ContactTransferRecord = {
      id: 1,
      contact_id: 7,
      group_id: 3,
      from_user_id: 1,
      to_user_id: 8,
      requested_by: 1,
      state: 'pending_recipient',
      senior_user_id: null,
      senior_decided_at: null,
      recipient_decided_at: null,
      force_assigned: false,
      comment: null,
      expires_at: '2026-12-31T00:00:00Z',
      version: 1,
      updated_at: '2026-05-16T00:00:00Z',
      created_at: '2026-05-16T00:00:00Z',
    }
    requestContactTransferMock.mockResolvedValue(transferRecord)

    const pinia = createPinia()

    setActivePinia(pinia)

  })



  it('uses card transfer hint for user role', () => {

    expect(transferHintForRole('user')).toContain('сразу перейдёт')

  })



  it('uses immediate assign hint for senior role', () => {

    expect(transferHintForRole('senior')).toContain('сразу назначена')

  })



  it('submits contact group transfer API', async () => {

    await requestContactTransfer(7, 3, { to_user_id: 8, comment: 'отпуск' })



    expect(requestContactTransferMock).toHaveBeenCalledWith(7, 3, {

      to_user_id: 8,

      comment: 'отпуск',

    })

  })

})


