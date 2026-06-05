import { flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'

import type { ContactTransferRecord } from '@/entities/contact/types'
import {
  acceptContactTransfer,
  approveContactTransfer,
  listContactTransfers,
} from '@/features/contacts/api'
import TransferInboxPanel from '@/features/contacts/transfer-card/TransferInboxPanel.vue'
import { AppError } from '@/shared/api/http'
import { useAuthStore } from '@/shared/store/auth'

vi.mock('@/features/contacts/api', () => ({
  listContactTransfers: vi.fn(),
  approveContactTransfer: vi.fn(),
  declineContactTransfer: vi.fn(),
  acceptContactTransfer: vi.fn(),
  rejectContactTransfer: vi.fn(),
  cancelContactTransfer: vi.fn(),
}))

vi.mock('@/shared/realtime/ws-client', () => ({
  getRealtimeWS: () => ({ onTopic: () => () => {} }),
}))

const listTransfersMock = vi.mocked(listContactTransfers)
const approveMock = vi.mocked(approveContactTransfer)
const acceptMock = vi.mocked(acceptContactTransfer)

const pendingSeniorRow: ContactTransferRecord = {
  id: 11,
  contact_id: 7,
  group_id: 3,
  from_user_id: 1,
  to_user_id: 2,
  requested_by: 1,
  state: 'pending_senior',
  senior_user_id: null,
  senior_decided_at: null,
  recipient_decided_at: null,
  force_assigned: false,
  comment: null,
  expires_at: '2026-12-31T00:00:00Z',
  version: 4,
  updated_at: '2026-05-17T10:00:00Z',
  created_at: '2026-05-17T09:00:00Z',
}

function mountPanel() {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().$patch({
    user: {
      id: 8,
      email: 'senior@crm.local',
      full_name: 'Senior',
      role: 'senior',
      department_id: 1,
      group_id: 1,
      presence: 'online',
      permissions: [],
    },
  })

  const Host = defineComponent({
    setup() {
      return () =>
        h(NConfigProvider, null, () =>
          h(NMessageProvider, null, () => h(TransferInboxPanel)),
        )
    },
  })

  return mount(Host)
}

describe('TransferInboxPanel', () => {
  beforeEach(() => {
    listTransfersMock.mockReset()
    approveMock.mockReset()
    acceptMock.mockReset()
    listTransfersMock.mockResolvedValue({ items: [pendingSeniorRow] })
  })

  it('passes expected_version on approve and reloads inbox after 409', async () => {
    approveMock.mockRejectedValue(
      new AppError(
        { code: 'conflict', message: 'Transfer was updated by another request' },
        409,
      ),
    )

    const wrapper = mountPanel()
    await flushPromises()

    const approveBtn = wrapper
      .findAll('button')
      .find((btn) => /одобрить/i.test(btn.text()))
    expect(approveBtn).toBeDefined()
    await approveBtn!.trigger('click')
    await flushPromises()

    expect(approveMock).toHaveBeenCalledWith(11, 4)
    // mount (2) + reload after 409 (2)
    expect(listTransfersMock).toHaveBeenCalledTimes(4)
  })

  it('passes expected_version on accept', async () => {
    const recipientRow: ContactTransferRecord = {
      ...pendingSeniorRow,
      id: 12,
      state: 'pending_recipient',
      to_user_id: 8,
    }
    listTransfersMock.mockResolvedValue({ items: [recipientRow] })
    acceptMock.mockResolvedValue(recipientRow)

    useAuthStore().$patch({
      user: {
        id: 8,
        email: 'u@crm.local',
        full_name: 'Recipient',
        role: 'user',
        department_id: 1,
        group_id: 1,
        presence: 'online',
        permissions: [],
      },
    })

    const wrapper = mountPanel()
    await flushPromises()

    const acceptBtn = wrapper
      .findAll('button')
      .find((btn) => /принять/i.test(btn.text()))
    expect(acceptBtn).toBeDefined()
    await acceptBtn!.trigger('click')
    await flushPromises()

    expect(acceptMock).toHaveBeenCalledWith(12, 4)
  })
})
