import type {
  AccountingAccountantOption,
  AccountingRequirement,
  AccountingUnit,
  AccountingUnitCategory,
  AccountingUnitOrderGroup,
  AccountingUnitOwnerRow,
} from '@/features/accounting/types'
import { http } from '@/shared/api/http'

export async function listAccountingUnits(): Promise<{
  items: AccountingUnit[]
  is_chief: boolean
}> {
  const { data } = await http.get<{ items: AccountingUnit[]; is_chief: boolean }>(
    '/accounting/units',
  )
  return data
}

export async function listAccountingUnitCategories(): Promise<AccountingUnitCategory[]> {
  const { data } = await http.get<{ items: AccountingUnitCategory[] }>(
    '/accounting/units/categories',
  )
  return data.items
}

export interface CreateAccountingUnitPayload {
  inn: string
  kpp: string
  name: string
  category_code: string
  commission_rate_percent: number
}

export async function createAccountingUnit(
  payload: CreateAccountingUnitPayload,
): Promise<AccountingUnit> {
  const { data } = await http.post<AccountingUnit>('/accounting/units', payload)
  return data
}

export async function listAccountingOrders(params: {
  supplier_inn?: string
  q?: string
  limit?: number
  offset?: number
}): Promise<{ items: AccountingUnitOrderGroup[]; total: number; limit: number; offset: number }> {
  const { data } = await http.get<{
    items: AccountingUnitOrderGroup[]
    total: number
    limit: number
    offset: number
  }>('/accounting/orders', { params })
  return data
}

export async function downloadAccountingRegistry(orderId: number): Promise<Blob> {
  const { data } = await http.get<Blob>(`/accounting/orders/${orderId}/registry`, {
    responseType: 'blob',
  })
  return data
}

export async function listAccountingRequirements(params: {
  supplier_inn?: string
  status?: string
  q?: string
  limit?: number
  offset?: number
}): Promise<{ items: AccountingRequirement[]; total: number; limit: number; offset: number }> {
  const { data } = await http.get<{
    items: AccountingRequirement[]
    total: number
    limit: number
    offset: number
  }>('/accounting/requirements', { params })
  return data
}

export async function downloadRequirementPdf(requirementId: number): Promise<Blob> {
  const { data } = await http.get<Blob>(`/accounting/requirements/${requirementId}/pdf`, {
    responseType: 'blob',
  })
  return data
}

export async function listAccountingUnitOwners(): Promise<{
  items: AccountingUnitOwnerRow[]
  accountants: AccountingAccountantOption[]
}> {
  const { data } = await http.get<{
    items: AccountingUnitOwnerRow[]
    accountants: AccountingAccountantOption[]
  }>('/accounting/assignments/units')
  return data
}

export async function assignAccountingUnitOwner(
  unitId: number,
  accountantUserId: number | null,
): Promise<AccountingUnitOwnerRow> {
  const { data } = await http.put<AccountingUnitOwnerRow>(
    `/accounting/assignments/units/${unitId}`,
    { accountant_user_id: accountantUserId },
  )
  return data
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
