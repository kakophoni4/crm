import { http } from '@/shared/api/http'

import type {
  LawyerAlert,
  LawyerDirector,
  LawyerPayment,
  LawyerRegistryTree,
  LawyerShop,
} from './types'

export type {
  LawyerAlert,
  LawyerDirector,
  LawyerPayment,
  LawyerRegistryTree,
  LawyerShop,
} from './types'

export interface RegistryFilters {
  q?: string
  kind?: string | null
  company_status?: string | null
  unreliable?: string | null
  zsk?: string | null
  ecsp_status?: string | null
  manager?: string
  dirovod?: string
  include_hidden?: boolean
}

export async function listLawyerRegistry(filters?: RegistryFilters): Promise<LawyerRegistryTree> {
  const { data } = await http.get<LawyerRegistryTree>('/lawyer-registry', {
    params: {
      q: filters?.q || undefined,
      kind: filters?.kind || undefined,
      company_status: filters?.company_status || undefined,
      unreliable: filters?.unreliable || undefined,
      zsk: filters?.zsk || undefined,
      ecsp_status: filters?.ecsp_status || undefined,
      manager: filters?.manager || undefined,
      dirovod: filters?.dirovod || undefined,
      include_hidden: filters?.include_hidden || undefined,
    },
  })
  return data
}

export async function getLawyerDirector(id: number): Promise<LawyerDirector> {
  const { data } = await http.get<LawyerDirector>(`/lawyer-registry/directors/${id}`)
  return data
}

export async function createLawyerDirector(body: Record<string, unknown>): Promise<LawyerDirector> {
  const { data } = await http.post<LawyerDirector>('/lawyer-registry/directors', body)
  return data
}

export async function patchLawyerDirector(
  id: number,
  body: Record<string, unknown>,
): Promise<LawyerDirector> {
  const { data } = await http.patch<LawyerDirector>(`/lawyer-registry/directors/${id}`, body)
  return data
}

export async function createLawyerShop(body: Record<string, unknown>): Promise<LawyerShop> {
  const { data } = await http.post<LawyerShop>('/lawyer-registry/shops', body)
  return data
}

export async function patchLawyerShop(
  id: number,
  body: Record<string, unknown>,
): Promise<LawyerShop> {
  const { data } = await http.patch<LawyerShop>(`/lawyer-registry/shops/${id}`, body)
  return data
}

export async function addLawyerPayment(
  directorId: number,
  body: { shop_id?: number | null; period_ym: string; amount: number; note?: string | null },
): Promise<LawyerPayment> {
  const { data } = await http.post<LawyerPayment>(
    `/lawyer-registry/directors/${directorId}/payments`,
    body,
  )
  return data
}

export async function deleteLawyerPayment(id: number): Promise<void> {
  await http.delete(`/lawyer-registry/payments/${id}`)
}

export async function listLawyerAlerts(): Promise<{ items: LawyerAlert[]; unread: number }> {
  const { data } = await http.get<{ items: LawyerAlert[]; unread: number }>(
    '/lawyer-registry/alerts',
  )
  return data
}

export async function markLawyerAlertsRead(ids?: number[]): Promise<void> {
  await http.post('/lawyer-registry/alerts/read', { ids: ids ?? null })
}

export async function importLawyerSvodnaya(file: File): Promise<{
  directors: number
  shops: number
  payments: number
  updated: number
}> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<{
    directors: number
    shops: number
    payments: number
    updated: number
  }>('/lawyer-registry/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180_000,
  })
  return data
}
