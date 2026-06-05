import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  acceptContactTransfer,
  approveContactTransfer,
  cancelContactTransfer,
  declineContactTransfer,
  listContactTransfers,
  rejectContactTransfer,
} from '@/features/contacts/api'
import { useAuthStore } from '@/shared/store/auth'

vi.mock('@/features/contacts/api', () => ({
  listContactTransfers: vi.fn(),
  approveContactTransfer: vi.fn(),
  declineContactTransfer: vi.fn(),
  acceptContactTransfer: vi.fn(),
  rejectContactTransfer: vi.fn(),
  cancelContactTransfer: vi.fn(),
}))

const listTransfersMock = vi.mocked(listContactTransfers)
const approveMock = vi.mocked(approveContactTransfer)
const declineMock = vi.mocked(declineContactTransfer)
const acceptMock = vi.mocked(acceptContactTransfer)
const rejectMock = vi.mocked(rejectContactTransfer)
const cancelMock = vi.mocked(cancelContactTransfer)

describe('contact transfer inbox api', () => {
  beforeEach(() => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().$patch({
      user: {
        id: 8,
        email: 'u@crm.local',
        full_name: 'Operator',
        role: 'senior',
        department_id: 1,
        group_id: 1,
        presence: 'online',
        permissions: [],
      },
    })
    listTransfersMock.mockReset()
    approveMock.mockReset()
    declineMock.mockReset()
    acceptMock.mockReset()
    rejectMock.mockReset()
    cancelMock.mockReset()
  })

  it('loads both pending_senior and pending_recipient buckets', async () => {
    listTransfersMock
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({ items: [] })

    await listContactTransfers({ state: 'pending_senior' })
    await listContactTransfers({ state: 'pending_recipient' })

    expect(listTransfersMock).toHaveBeenNthCalledWith(1, { state: 'pending_senior' })
    expect(listTransfersMock).toHaveBeenNthCalledWith(2, { state: 'pending_recipient' })
  })

  it('supports inbox actions approve/decline/accept/reject/cancel', async () => {
    approveMock.mockResolvedValue({} as never)
    declineMock.mockResolvedValue({} as never)
    acceptMock.mockResolvedValue({} as never)
    rejectMock.mockResolvedValue({} as never)
    cancelMock.mockResolvedValue({} as never)

    await approveContactTransfer(1, 2)
    await declineContactTransfer(2)
    await acceptContactTransfer(3, 5)
    await rejectContactTransfer(4)
    await cancelContactTransfer(5)

    expect(approveMock).toHaveBeenCalledWith(1, 2)
    expect(declineMock).toHaveBeenCalledWith(2)
    expect(acceptMock).toHaveBeenCalledWith(3, 5)
    expect(rejectMock).toHaveBeenCalledWith(4)
    expect(cancelMock).toHaveBeenCalledWith(5)
  })
})
