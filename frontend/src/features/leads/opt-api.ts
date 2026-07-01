import type { OptOrder, OptOrderListResponse } from '@/features/leads/opt-types'
import { http } from '@/shared/api/http'

export async function listOptOrders(leadId: number): Promise<OptOrder[]> {
  const { data } = await http.get<OptOrderListResponse>(`/leads/${leadId}/opt-orders`)
  return data.items
}

export async function uploadOptApplication(leadId: number, file: File): Promise<OptOrder> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<OptOrder>(`/leads/${leadId}/opt-orders/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function retryOptOrder(leadId: number, orderId: number): Promise<OptOrder> {
  const { data } = await http.post<OptOrder>(`/leads/${leadId}/opt-orders/${orderId}/retry`)
  return data
}

export async function deleteOptOrder(leadId: number, orderId: number): Promise<void> {
  await http.delete(`/leads/${leadId}/opt-orders/${orderId}`)
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

export async function addOptOrderPayment(
  leadId: number,
  orderId: number,
  body: {
    amount: number
    paid_at: string
    payment_type: 'card' | 'crypto' | 'wire' | 'cash'
    recipient: 'orange' | 'beneficiary'
  },
): Promise<OptOrder> {
  const { data } = await http.post<OptOrder>(
    `/leads/${leadId}/opt-orders/${orderId}/payments`,
    body,
  )
  return data
}
