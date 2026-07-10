export interface OptCounterparty {
  inn: string
  kpp?: string | null
  name?: string | null
}

export interface OptOrderLine {
  id: number
  crm_id: string
  line_no: number
  supplier: OptCounterparty
  document_date: string
  amount: number
  vat_amount: number
  amount_without_vat: number
  document_number?: string | null
}

export interface OptVolumeCategoryBreakdown {
  label: string
  volume: number
  rate_percent: number
  commission: number
}

export interface OptPaymentDocument {
  file_id: number
  name?: string | null
}

export interface OptPayment {
  id: number
  amount: number
  paid_at: string
  payment_type: 'card' | 'crypto' | 'wire' | 'cash'
  recipient: 'orange' | 'beneficiary'
  created_at: string
  document_file_id?: number | null
  document_name?: string | null
  documents?: OptPaymentDocument[]
}

export interface OptCommissionHistoryItem {
  id: number
  old_commission_due: number
  new_commission_due: number
  delta: number
  direction: 'increase' | 'decrease' | string
  changed_by: number
  changed_by_name?: string | null
  created_at: string
}

export interface OptOrderExistingRef {
  lead_id: number
  order_id: number
  order_no: number
}

export interface OptAttachmentProbeResult {
  is_application: boolean
  buyer_inn?: string | null
  line_count?: number | null
  existing_order?: OptOrderExistingRef | null
}

export interface OptOrder {
  id: number
  lead_id: number
  order_no: number
  crm_id: string
  status: 'queued' | 'submitting' | 'submitted' | 'failed' | string
  payment_status: 'unpaid' | 'partial' | 'paid' | string
  total_volume: number
  commission_base: number
  commission_adjustment: number
  commission_due: number
  amount_paid: number
  amount_remaining: number
  volume_by_category: Record<string, OptVolumeCategoryBreakdown>
  buyer: OptCounterparty
  source_filename?: string | null
  submission_error?: string | null
  submitted_at?: string | null
  created_at: string
  lines: OptOrderLine[]
  payments: OptPayment[]
  commission_history?: OptCommissionHistoryItem[]
}

export interface OptOrderListResponse {
  items: OptOrder[]
}

export interface OptOrderRegistryItem {
  id: number
  lead_id: number
  order_no: number
  chat_id?: number | null
  contact_id?: number | null
  contact_name?: string | null
  group_id: number
  group_name?: string | null
  department_id?: number | null
  department_name?: string | null
  status: string
  payment_status: string
  total_volume: number
  commission_due: number
  amount_paid: number
  amount_remaining: number
  buyer: OptCounterparty
  source_filename?: string | null
  created_at: string
  lines_count: number
  payments_count: number
}

export interface OptOrderRegistryListResponse {
  items: OptOrderRegistryItem[]
  total: number
}

export const OPT_PAYMENT_TYPE_OPTIONS = [
  { label: 'На карту', value: 'card' as const },
  { label: 'Крипта', value: 'crypto' as const },
  { label: 'Безнал', value: 'wire' as const },
  { label: 'Кэш', value: 'cash' as const },
]

export const OPT_PAYMENT_RECIPIENT_OPTIONS = [
  { label: 'Оранж', value: 'orange' as const },
  { label: 'Бенефициар', value: 'beneficiary' as const },
]

export function optPaymentTypeLabel(value: string): string {
  return OPT_PAYMENT_TYPE_OPTIONS.find((row) => row.value === value)?.label ?? value
}

export function optPaymentRecipientLabel(value: string): string {
  return OPT_PAYMENT_RECIPIENT_OPTIONS.find((row) => row.value === value)?.label ?? value
}

export function optPaymentStatusLabel(status: string): string {
  if (status === 'paid') return 'оплачена'
  if (status === 'partial') return 'частично'
  return 'не оплачена'
}
