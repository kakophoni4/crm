export type LavokParserMark = 'new' | 'watching' | 'taking' | 'skip'

export interface LavokParserLot {
  id: number
  inn: string
  sheet_date: string
  source: string | null
  name: string | null
  price: string | null
  registered_at: string | null
  tax: string | null
  address_director: string | null
  courts: string | null
  debts: string | null
  egrul_reliability: string | null
  bankruptcy: string | null
  turnover: string | null
  reporting: string | null
  leasing: string | null
  zsk: string | null
  summary: string | null
  score: string | null
  first_seen: string | null
  seller: string | null
  link: string | null
  companium: string | null
  egrul_status: string | null
  mark: LavokParserMark | string
  note: string | null
  is_deleted: boolean
  created_at: string
  updated_at: string
}

export interface LavokParserListResponse {
  items: LavokParserLot[]
  total: number
  sheet_dates: string[]
  sheet_date: string | null
}

export interface LavokParserIngestResponse {
  sheets: number
  upserted: number
  created: number
  updated: number
}

export const LAVOK_MARK_OPTIONS = [
  { label: 'Новая', value: 'new' },
  { label: 'Смотрю', value: 'watching' },
  { label: 'Беру', value: 'taking' },
  { label: 'Пропуск', value: 'skip' },
]
