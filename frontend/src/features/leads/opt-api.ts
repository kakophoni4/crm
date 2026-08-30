import type {
  OptAttachmentProbeResult,
  OptOrder,
  OptOrderListResponse,
  OptOrderRegistryListResponse,
  OptPaymentLedgerListResponse,
  OptRegistryManagerItem,
  OptRegistryManagersResponse,
  OptSync1cResponse,
} from '@/features/leads/opt-types'
import { http } from '@/shared/api/http'

export async function listOptOrders(
  leadId: number,
  options: { signal?: AbortSignal } = {},
): Promise<OptOrder[]> {
  const { data } = await http.get<OptOrderListResponse>(`/leads/${leadId}/opt-orders`, {
    signal: options.signal,
  })
  return data.items
}

export async function listOptOrdersRegistry(params?: {
  department_id?: number
  group_id?: number
  contact_id?: number
  chat_id?: number
  payment_status?: string
  period_code?: string
  manager_user_id?: number
  q?: string
  open_only?: boolean
  kind?: string
  offset?: number
  limit?: number
}): Promise<OptOrderRegistryListResponse> {
  const { data } = await http.get<OptOrderRegistryListResponse>('/opt-orders', { params })
  return data
}

export async function listOptOrderManagers(params?: {
  department_id?: number
  group_id?: number
  period_code?: string
  kind?: string
}): Promise<OptRegistryManagerItem[]> {
  const { data } = await http.get<OptRegistryManagersResponse>('/opt-orders/managers', { params })
  return data.items
}

export async function patchOptOrderPeriod(
  orderId: number,
  periodCode: string,
): Promise<{ order_id: number; lead_id: number; period_code: string }> {
  const { data } = await http.patch<{ order_id: number; lead_id: number; period_code: string }>(
    `/opt-orders/${orderId}/period`,
    { period_code: periodCode },
  )
  return data
}

export async function syncOptOrdersWith1c(
  periodCode?: string | null,
): Promise<OptSync1cResponse> {
  // Full sync across periods can take minutes — default axios timeout is 15s.
  const { data } = await http.post<OptSync1cResponse>(
    '/opt-orders/sync-1c',
    { period_code: periodCode?.trim() ? periodCode.trim() : null },
    { timeout: 600_000 },
  )
  return data
}

export async function listOptPaymentsLedger(params?: {
  department_id?: number
  group_id?: number
  contact_id?: number
  payment_type?: string
  payment_status?: string
  period_code?: string
  manager_user_id?: number
  q?: string
  kind?: string
  offset?: number
  limit?: number
}): Promise<OptPaymentLedgerListResponse> {
  const { data } = await http.get<OptPaymentLedgerListResponse>('/opt-payments', { params })
  return data
}

export async function uploadOptApplication(
  leadId: number,
  file: File,
): Promise<OptOrder> {
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
  body: {
    chat_id: number
    message_id: number
    attachment_index: number
    period_code?: string
  },
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

export interface OptReceiptItem {
  id: number
  supplier_inn: string
  supplier_name?: string | null
  period_code: string
  doc_kind: string
  is_correction?: boolean
  source_filename: string
  has_pdf: boolean
}

export async function listOptOrderReceipts(
  leadId: number,
  orderId: number,
): Promise<{ items: OptReceiptItem[]; available: boolean }> {
  const { data } = await http.get<{ items: OptReceiptItem[]; available: boolean }>(
    `/leads/${leadId}/opt-orders/${orderId}/receipts`,
  )
  return data
}

export async function downloadOptOrderReceiptsArchive(
  leadId: number,
  orderId: number,
): Promise<Blob> {
  const { data } = await http.get<Blob>(`/leads/${leadId}/opt-orders/${orderId}/receipts/archive`, {
    responseType: 'blob',
  })
  return data
}

export async function sendOptOrderReceiptsToClient(
  leadId: number,
  orderId: number,
): Promise<void> {
  await http.post(`/leads/${leadId}/opt-orders/${orderId}/send-receipts`)
}

export interface OptSalesBookExtractItem {
  id: number
  seller_inn: string
  buyer_inn: string
  seller_name?: string | null
  buyer_name?: string | null
  source_filename: string
  has_pdf: boolean
}

export async function listOptOrderSalesBookExtracts(
  leadId: number,
  orderId: number,
): Promise<{ items: OptSalesBookExtractItem[]; available: boolean }> {
  const { data } = await http.get<{ items: OptSalesBookExtractItem[]; available: boolean }>(
    `/leads/${leadId}/opt-orders/${orderId}/sales-book-extracts`,
  )
  return data
}

export async function downloadOptOrderSalesBooksArchive(
  leadId: number,
  orderId: number,
): Promise<Blob> {
  const { data } = await http.get<Blob>(
    `/leads/${leadId}/opt-orders/${orderId}/sales-book-extracts/archive`,
    { responseType: 'blob' },
  )
  return data
}

export async function sendOptOrderSalesBooksToClient(
  leadId: number,
  orderId: number,
): Promise<void> {
  await http.post(`/leads/${leadId}/opt-orders/${orderId}/send-sales-book`)
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
