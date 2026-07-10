import type {
  OptAttachmentProbeResult,
  OptOrder,
  OptOrderListResponse,
  OptOrderRegistryListResponse,
} from '@/features/leads/opt-types'
import { http } from '@/shared/api/http'

export async function listOptOrders(leadId: number): Promise<OptOrder[]> {
  const { data } = await http.get<OptOrderListResponse>(`/leads/${leadId}/opt-orders`)
  return data.items
}

export async function listOptOrdersRegistry(params?: {
  department_id?: number
  group_id?: number
  payment_status?: string
  open_only?: boolean
  offset?: number
  limit?: number
}): Promise<OptOrderRegistryListResponse> {
  const { data } = await http.get<OptOrderRegistryListResponse>('/opt-orders', { params })
  return data
}

export async function uploadOptApplication(leadId: number, file: File): Promise<OptOrder> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<OptOrder>(`/leads/${leadId}/opt-orders/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function probeOptChatAttachment(
  leadId: number,
  body: { chat_id: number; message_id: number; attachment_index: number },
): Promise<OptAttachmentProbeResult> {
  const { data } = await http.post(
    `/leads/${leadId}/opt-orders/probe-attachment`,
    body,
  )
  return data
}

export async function uploadOptFromChatAttachment(
  leadId: number,
  body: { chat_id: number; message_id: number; attachment_index: number },
): Promise<OptOrder> {
  const { data } = await http.post<OptOrder>(
    `/leads/${leadId}/opt-orders/upload-from-attachment`,
    body,
  )
  return data
}

export async function adjustOptOrderCommission(
  leadId: number,
  orderId: number,
  body: {
    amount: number
    direction: 'increase' | 'decrease'
  },
): Promise<OptOrder> {
  const { data } = await http.patch<OptOrder>(
    `/leads/${leadId}/opt-orders/${orderId}/commission`,
    body,
  )
  return data
}

export async function deleteOptOrder(leadId: number, orderId: number): Promise<void> {
  await http.delete(`/leads/${leadId}/opt-orders/${orderId}`)
}

export async function deleteOptOrderLine(
  leadId: number,
  orderId: number,
  lineId: number,
): Promise<OptOrder> {
  const { data } = await http.delete<OptOrder>(
    `/leads/${leadId}/opt-orders/${orderId}/lines/${lineId}`,
  )
  return data
}

export async function sendOptRegistryToClient(
  leadId: number,
  orderId: number,
): Promise<{ message_id: number; chat_id: number }> {
  const { data } = await http.post<{ message_id: number; chat_id: number }>(
    `/leads/${leadId}/opt-orders/${orderId}/send-registry`,
  )
  return data
}

export async function downloadOptRegistry(leadId: number, orderId: number): Promise<Blob> {
  const { data } = await http.get<Blob>(`/leads/${leadId}/opt-orders/${orderId}/registry`, {
    responseType: 'blob',
  })
  return data
}

export async function downloadOptPaymentDocument(
  leadId: number,
  orderId: number,
  paymentId: number,
  fileId?: number | null,
): Promise<Blob> {
  const { data } = await http.get<Blob>(
    `/leads/${leadId}/opt-orders/${orderId}/payments/${paymentId}/document`,
    {
      responseType: 'blob',
      params: fileId != null ? { file_id: fileId } : undefined,
    },
  )
  return data
}

export async function addOptOrderPayment(
  leadId: number,
  orderId: number,
  body: {
    amount: number
    paid_at: string
    payment_type: 'card' | 'crypto' | 'wire' | 'cash'
    recipient: 'orange' | 'beneficiary'
    document_file_id?: number | null
    document_file_ids?: number[]
  },
): Promise<OptOrder> {
  const { data } = await http.post<OptOrder>(
    `/leads/${leadId}/opt-orders/${orderId}/payments`,
    body,
  )
  return data
}
