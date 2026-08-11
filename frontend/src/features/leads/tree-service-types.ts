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

/** One billable row — same type may appear multiple times with different unit prices. */
export interface TreeOrderLine {
  id: string
  type: string
  /** Price for one unit. */
  unit_price?: number | null
  quantity?: number | null
  /** Legacy total (migrated into unit_price). */
  cost?: number | null
}

export interface TreePayment {
  id: string
  amount: number
  paid_at: string
  payment_type: 'card' | 'crypto' | 'wire' | 'cash'
  recipient: 'orange' | 'beneficiary'
}

export function treeLineTotal(line: TreeOrderLine): number {
  const qty = Number(line.quantity || 0)
  const unit = Number(line.unit_price ?? 0)
  if (qty > 0 && unit >= 0) return qty * unit
  return 0
}

export function newTreeLineId(): string {
  return `tl-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}
