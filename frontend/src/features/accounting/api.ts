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
  kpp?: string | null
  name: string
  category_code: string
  commission_rate_percent: number
  period_codes: string[]
}

export interface PatchAccountingUnitPayload {
  commission_rate_percent?: number
  volume_limit?: number | null
  clear_volume_limit?: boolean
  name?: string
  category_code?: string
  period_codes?: string[]
  is_active?: boolean
}

export async function createAccountingUnit(
  payload: CreateAccountingUnitPayload,
): Promise<AccountingUnit> {
  const { data } = await http.post<AccountingUnit>('/accounting/units', payload)
  return data
}

export async function patchAccountingUnit(
  unitId: number,
  payload: PatchAccountingUnitPayload,
): Promise<AccountingUnit> {
  const { data } = await http.patch<AccountingUnit>(`/accounting/units/${unitId}`, payload)
  return data
}

export async function deleteAccountingUnit(unitId: number): Promise<void> {
  await http.delete(`/accounting/units/${unitId}`)
}

export async function listAccountingOrders(params: {
  supplier_inn?: string
  q?: string
  period_code?: string
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

export async function patchAccountingOrderPeriod(
  orderId: number,
  periodCode: string,
): Promise<{ order_id: number; period_code: string }> {
  const { data } = await http.patch<{ order_id: number; period_code: string }>(
    `/accounting/orders/${orderId}/period`,
    { period_code: periodCode },
  )
  return data
}

export async function listAccountingRequirements(params: {
  supplier_inn?: string
  /** new | answered | replied (ответ ушёл в СБИС) */
  status?: 'new' | 'answered' | 'replied' | string
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

export async function syncAccountingRequirements(): Promise<{
  fetched: number
  created: number
  existing: number
  failed: number
  marked_synced: number
  skipped_non_pdf?: number
  queued?: boolean
  errors: string[]
}> {
  const { data } = await http.post<{
    fetched: number
    created: number
    existing: number
    failed: number
    marked_synced: number
    skipped_non_pdf?: number
    queued?: boolean
    errors: string[]
  }>('/accounting/requirements/sync')
  return data
}

export async function patchAccountingRequirementStatus(
  requirementId: number,
  status: 'new' | 'answered',
): Promise<AccountingRequirement> {
  const { data } = await http.patch<AccountingRequirement>(
    `/accounting/requirements/${requirementId}`,
    { status },
  )
  return data
}

export async function replyAccountingRequirement(
  requirementId: number,
  files: File[],
  dryRun = false,
): Promise<{
  id: number
  reply_status: string
  reply_error?: string | null
  replied_at?: string | null
  dry_run: boolean
  success: boolean
}> {
  const form = new FormData()
  form.append('dry_run', dryRun ? 'true' : 'false')
  for (const file of files) form.append('files', file)
  const { data } = await http.post<{
    id: number
    reply_status: string
    reply_error?: string | null
    replied_at?: string | null
    dry_run: boolean
    success: boolean
  }>(`/accounting/requirements/${requirementId}/reply`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 200000,
  })
  return data
}

export async function listAccountingTaskAssignees(): Promise<
  { id: number; full_name: string; role: string }[]
> {
  const { data } = await http.get<{ items: { id: number; full_name: string; role: string }[] }>(
    '/accounting/task-assignees',
  )
  return data.items
}

export async function createTaskFromRequirement(
  requirementId: number,
  payload: {
    unit_inn?: string | null
    assignee_id: number
    title: string
    description?: string | null
    due_at?: string | null
    file_ids?: number[]
    task_type?: string
  },
): Promise<unknown> {
  const { data } = await http.post(`/accounting/requirements/${requirementId}/tasks`, payload)
  return data
}

export async function fetchRequirementsDueSummary(): Promise<{
  overdue: number
  due_soon: number
  unanswered: number
}> {
  const { data } = await http.get<{ overdue: number; due_soon: number; unanswered: number }>(
    '/accounting/requirements/due-summary',
  )
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
