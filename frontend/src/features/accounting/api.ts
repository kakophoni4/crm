import type {
  AccountingAssignment,
  AccountingOrderLine,
  AccountingRequirement,
  AccountingUnit,
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

export async function listAccountingOrders(params: {
  supplier_inn?: string
  status?: string
  q?: string
  limit?: number
  offset?: number
}): Promise<{ items: AccountingOrderLine[]; total: number; limit: number; offset: number }> {
  const { data } = await http.get<{
    items: AccountingOrderLine[]
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

export async function listAccountingAssignments(): Promise<{ items: AccountingAssignment[] }> {
  const { data } = await http.get<{ items: AccountingAssignment[] }>('/accounting/assignments')
  return data
}

export async function updateAccountingAssignments(
  userId: number,
  unitIds: number[],
): Promise<AccountingAssignment> {
  const { data } = await http.put<AccountingAssignment>(`/accounting/assignments/${userId}`, {
    unit_ids: unitIds,
  })
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
