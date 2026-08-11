export interface TreeServiceTypeOption {
  type_code: string
  label: string
  unit_price: number | null
  is_active: boolean
}

/** Fallback catalog if API unavailable. */
export const TREE_SERVICE_TYPE_FALLBACK: TreeServiceTypeOption[] = [
  { type_code: 'archive_extract', label: 'Архивная выписка', unit_price: null, is_active: true },
  { type_code: 'book', label: 'Книга', unit_price: null, is_active: true },
  { type_code: 'tree', label: 'Дерево', unit_price: null, is_active: true },
  { type_code: 'base', label: 'База', unit_price: null, is_active: true },
  { type_code: 'sur', label: 'СУР', unit_price: null, is_active: true },
  { type_code: 'other', label: 'Другое', unit_price: null, is_active: true },
  { type_code: 'deposit', label: 'Депозит', unit_price: null, is_active: true },
]

export interface TreeOrderLine {
  type: string
  quantity?: number | null
  cost?: number | null
}

export interface TreePayment {
  id: string
  amount: number
  paid_at: string
  payment_type: 'card' | 'crypto' | 'wire' | 'cash'
  recipient: 'orange' | 'beneficiary'
}
