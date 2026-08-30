export type ShopKind = 'priority' | 'service' | 'new' | string

export interface LawyerShop {
  id: number
  inn: string
  name: string
  director_id: number | null
  director_name: string | null
  kind: ShopKind
  registered_at: string | null
  planned_payout: number | null
  company_status: string | null
  sale_priority: string | null
  unreliable: string | null
  treatment_status: string | null
  ecsp_status: string | null
  ecsp_until: string | null
  zsk: string | null
  banks: string | null
  accounts_status: string | null
  manager: string | null
  phone: string | null
  telegram: string | null
  accountant: string | null
  comment: string | null
  source: string
  last_parser_at: string | null
  pinned_at: string | null
  created_at: string
}

export interface LawyerPayment {
  id: number
  director_id: number
  shop_id: number | null
  shop_name: string | null
  period_ym: string
  amount: number
  paid_at: string | null
  note: string | null
  created_at: string
}

export interface LawyerDirector {
  id: number
  full_name: string
  salary_plan: number | null
  dirovod: string | null
  company_status: string | null
  companies_status: string | null
  ecsp_status: string | null
  ecsp_until: string | null
  banks: string | null
  accounts_status: string | null
  phone: string | null
  telegram: string | null
  passport: string | null
  inn_personal: string | null
  snils: string | null
  birth_date: string | null
  in_touch: string | null
  note: string | null
  pinned_at: string | null
  shop_count: number
  last_paid_period: string | null
  shops: LawyerShop[]
  payments: LawyerPayment[]
}

export interface LawyerRegistryTree {
  items: LawyerDirector[]
  orphan_shops: LawyerShop[]
  pinned_shops: LawyerShop[]
  total_directors: number
  total_shops: number
  unread_alerts: number
}

export interface LawyerAlert {
  id: number
  shop_id: number | null
  inn: string
  title: string
  details: string | null
  is_read: boolean
  created_at: string
}

export const SHOP_KIND_OPTIONS = [
  { label: 'Приоритетная', value: 'priority' },
  { label: 'Обслуживающая', value: 'service' },
  { label: 'Новая', value: 'new' },
]

export const COMPANY_STATUS_OPTIONS = [
  'Активна',
  'В процессе ликвидации',
  'Ликвидирована',
  'Утиль',
  'Потеряна',
  'Отстойник',
].map((value) => ({ label: value, value }))

export const ZSK_OPTIONS = [
  'Зеленый',
  'Желтый',
  'Желтый + тип',
  'Красный',
].map((value) => ({ label: value, value }))

export const ECSP_OPTIONS = [
  'Есть',
  'Отозвана',
  'не найдена',
  'Надо делать',
].map((value) => ({ label: value, value }))

export const UNRELIABLE_OPTIONS = [
  'Налог',
  'Адрес',
  'Должност.лицо',
].map((value) => ({ label: value, value }))
