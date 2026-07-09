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

export interface OptPayment {
  id: number
  amount: number
  paid_at: string
  payment_type: 'card' | 'crypto' | 'wire' | 'cash'
  recipient: 'orange' | 'beneficiary'
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
}

export interface OptOrderListResponse {
  items: OptOrder[]
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
