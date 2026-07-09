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
  is_active: boolean
}

export interface AccountingOrderLine {
  line_id: number
  line_no: number
  order_id: number
  lead_id: number
  order_no: number
  crm_id: string
  status: string
  payment_status: string
  supplier: AccountingSupplier
  buyer_inn: string
  buyer_name?: string | null
  document_date: string
  amount: number
  manager_user_id?: number | null
  manager_full_name?: string | null
  contact_name?: string | null
  source_filename?: string | null
  submitted_at?: string | null
  created_at: string
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

export interface AccountingAssignment {
  user_id: number
  user_full_name: string
  unit_ids: number[]
}

export const OPT_STATUS_LABELS: Record<string, string> = {
  draft: 'черновик',
  queued: 'в очереди',
  submitting: 'отправка',
  submitted: 'в 1С',
  failed: 'ошибка',
}

export const OPT_PAYMENT_STATUS_LABELS: Record<string, string> = {
  unpaid: 'не оплачена',
  partial: 'частично',
  paid: 'оплачена',
}
