export interface AccountingSupplier {
  inn: string
  kpp?: string | null
  name?: string | null
  category_code?: string | null
}

export interface AccountingUnit {
  id: number
  inn: string
  kpp?: string | null
  name?: string | null
  category_code?: string | null
  commission_rate_percent?: number | null
  volume_limit?: number | null
  is_active: boolean
  period_codes?: string[]
}

export interface AccountingUnitCategory {
  code: string
  label: string
  base_rate_percent?: number | null
}

export interface AccountingOrderLineBrief {
  line_id: number
  line_no: number
  document_date: string
  amount: number
  document_number?: string | null
}

export interface AccountingUnitOrder {
  order_id: number
  lead_id: number
  order_no: number
  crm_id: string
  status: string
  payment_status: string
  period_code?: string | null
  amount_paid: number
  commission_due: number
  lavka_line_volume: number
  line_count: number
  lines: AccountingOrderLineBrief[]
  buyer_inn: string
  buyer_name?: string | null
  source_filename?: string | null
  manager_user_id?: number | null
  manager_full_name?: string | null
  contact_name?: string | null
  submitted_at?: string | null
  created_at: string
  submission_error?: string | null
}

export interface AccountingUnitOrderGroup {
  unit: AccountingUnit
  orders: AccountingUnitOrder[]
  orders_count?: number
  orders_volume_sum?: number
}

export interface AccountingRequirement {
  id: number
  external_id: string
  supplier: AccountingSupplier
  title: string
  description?: string | null
  status: string
  has_pdf: boolean
  pdf_filename?: string | null
  metadata: Record<string, unknown>
  received_at: string
  created_at: string
}

export interface AccountingAccountantOption {
  user_id: number
  full_name: string
}

export interface AccountingUnitOwnerRow {
  unit_id: number
  inn: string
  name?: string | null
  category_code?: string | null
  commission_rate_percent?: number | null
  volume_limit?: number | null
  is_active: boolean
  period_codes?: string[]
  accountant_user_id?: number | null
  accountant_full_name?: string | null
}

export const OPT_STATUS_LABELS: Record<string, string> = {
  draft: 'черновик',
  queued: 'в очереди',
  submitting: 'отправка',
  submitted: 'в 1С',
  failed: 'ошибка',
}

export function formatAccountingPayment(
  amountPaid: number,
  commissionDue: number,
  paymentStatus: string,
): string {
  if (paymentStatus === 'paid' || (commissionDue > 0 && amountPaid >= commissionDue)) {
    return 'оплачена'
  }
  if (amountPaid <= 0) return 'не оплачена'
  return `${formatAccountingMoney(amountPaid)} / ${formatAccountingMoney(commissionDue)}`
}

export function formatAccountingMoney(value: number): string {
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    maximumFractionDigits: 2,
  }).format(value)
}
