import { env } from '@/shared/config/env'
import { http } from '@/shared/api/http'

import type {
  AnonymousShareResult,
  GroupChatFileGroupSummary,
  GroupChatFileList,
  LargeShareComplete,
  LargeShareInit,
  PublicShareInfo,
  ShareLink,
  ShareLinkCreateBody,
  VaultFile,
  VaultFileContent,
  VaultFileList,
  VaultFolderUserShare,
  VaultShareUser,
} from './types'

export type {
  AnonymousShareResult,
  GroupChatFile,
  GroupChatFileGroupSummary,
  GroupChatFileList,
  LargeShareComplete,
  LargeShareInit,
  PublicShareInfo,
  ShareLink,
  ShareLinkCreateBody,
  VaultFile,
  VaultFileContent,
  VaultFileList,
  VaultFolderUserShare,
  VaultShareUser,
} from './types'

export async function listVaultFiles(params?: {
  parent_id?: number | null
  offset?: number
  limit?: number
}): Promise<VaultFileList> {
  const { data } = await http.get<VaultFileList>('/storage/vault', {
    params: {
      parent_id: params?.parent_id ?? undefined,
      offset: params?.offset,
      limit: params?.limit,
    },
  })
  return data
}

export async function listSharedVaultFolders(): Promise<VaultFileList> {
  const { data } = await http.get<VaultFileList>('/storage/vault/shared')
  return data
}

export async function listVaultShareUsers(q?: string): Promise<VaultShareUser[]> {
  const { data } = await http.get<{ items: VaultShareUser[] }>('/storage/vault/share-users', {
    params: q?.trim() ? { q: q.trim() } : undefined,
  })
  return data.items
}

export async function listVaultFolderUserShares(folderId: number): Promise<VaultFolderUserShare[]> {
  const { data } = await http.get<{ items: VaultFolderUserShare[] }>(
    `/storage/vault/${folderId}/user-shares`,
  )
  return data.items
}

export async function shareVaultFolder(
  folderId: number,
  userId: number,
): Promise<VaultFolderUserShare> {
  const { data } = await http.post<VaultFolderUserShare>(`/storage/vault/${folderId}/user-shares`, {
    user_id: userId,
  })
  return data
}

export async function revokeVaultFolderUserShare(shareId: number): Promise<void> {
  await http.delete(`/storage/vault/user-shares/${shareId}`)
}

export async function createVaultFolder(body: {
  name: string
  parent_id?: number | null
}): Promise<VaultFile> {
  const { data } = await http.post<VaultFile>('/storage/vault/folders', {
    name: body.name,
    parent_id: body.parent_id ?? null,
  })
  return data
}

export async function uploadVaultFile(
  file: File,
  opts?: { parent_id?: number | null },
): Promise<VaultFile> {
  const form = new FormData()
  form.append('file', file)
  if (opts?.parent_id != null) {
    form.append('parent_id', String(opts.parent_id))
  }
  const { data } = await http.post<VaultFile>('/storage/vault', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return data
}

export async function deleteVaultFile(vaultId: number): Promise<void> {
  await http.delete(`/storage/vault/${vaultId}`)
}

export async function downloadVaultFile(vaultId: number): Promise<Blob> {
  const { data } = await http.get<Blob>(`/storage/vault/${vaultId}/download`, {
    responseType: 'blob',
  })
  return data
}

export async function renameVaultFile(
  vaultId: number,
  originalName: string,
): Promise<VaultFile> {
  const { data } = await http.patch<VaultFile>(`/storage/vault/${vaultId}`, {
    original_name: originalName,
  })
  return data
}

export async function getVaultFileContent(vaultId: number): Promise<VaultFileContent> {
  const { data } = await http.get<VaultFileContent>(`/storage/vault/${vaultId}/content`)
  return data
}

export async function updateVaultFileContent(
  vaultId: number,
  content: string,
): Promise<VaultFile> {
  const { data } = await http.put<VaultFile>(`/storage/vault/${vaultId}/content`, { content })
  return data
}

export async function createVaultShareLink(
  fileId: number,
  body: ShareLinkCreateBody,
): Promise<ShareLink> {
  const { data } = await http.post<ShareLink>(`/storage/vault/${fileId}/shares`, body, {
    timeout: 30_000,
  })
  return data
}

export async function revokeShareLink(shareId: number): Promise<void> {
  await http.delete(`/storage/shares/${shareId}`)
}

export async function listGroupFileGroups(): Promise<{ items: GroupChatFileGroupSummary[] }> {
  const { data } = await http.get<{ items: GroupChatFileGroupSummary[] }>(
    '/storage/group-files/groups',
  )
  return data
}

export async function listGroupFiles(params?: {
  group_id?: number
  chat_id?: number
  offset?: number
  limit?: number
}): Promise<GroupChatFileList> {
  const { data } = await http.get<GroupChatFileList>('/storage/group-files', { params })
  return data
}

export async function downloadGroupFile(fileRowId: number): Promise<Blob> {
  const { data } = await http.get<Blob>(`/storage/group-files/${fileRowId}/download`, {
    responseType: 'blob',
  })
  return data
}

export async function createAnonymousShare(
  file: File,
  options: {
    expires_in_hours?: number | null
    max_downloads?: number | null
    password?: string | null
  },
): Promise<AnonymousShareResult> {
  const form = new FormData()
  form.append('file', file)
  if (options.expires_in_hours != null) {
    form.append('expires_in_hours', String(options.expires_in_hours))
  }
  if (options.max_downloads != null) {
    form.append('max_downloads', String(options.max_downloads))
  }
  if (options.password) {
    form.append('password', options.password)
  }
  const { data } = await http.post<AnonymousShareResult>('/public/storage/share', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return data
}

export async function getPublicShareInfo(token: string): Promise<PublicShareInfo> {
  const { data } = await http.get<PublicShareInfo>(`/public/storage/shares/${token}`)
  return data
}

export async function downloadPublicShare(
  token: string,
  password?: string | null,
): Promise<Blob> {
  const { data } = await http.post<Blob>(
    `/public/storage/shares/${token}/download`,
    { password: password ?? null },
    { responseType: 'blob' },
  )
  return data
}

export function publicShareFileUrl(token: string): string {
  const base = String(env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
  return `${base}/public/storage/shares/${token}/file`
}

export async function initAdminLargeShare(body: {
  original_name: string
  mime_type: string
  size_bytes: number
  parent_id?: number | null
}): Promise<LargeShareInit> {
  const { data } = await http.post<LargeShareInit>(
    '/storage/admin/large-share/init',
    {
      original_name: body.original_name,
      mime_type: body.mime_type || 'application/octet-stream',
      size_bytes: body.size_bytes,
      parent_id: body.parent_id ?? null,
      expires_in_hours: 72,
      max_downloads: 1,
    },
    { timeout: 60_000 },
  )
  return data
}

export async function uploadAdminLargeSharePart(
  uploadId: number,
  partNumber: number,
  blob: Blob,
): Promise<{ part_number: number; uploaded_bytes: number }> {
  const form = new FormData()
  form.append('file', blob, `part-${partNumber}`)
  const { data } = await http.post<{ part_number: number; uploaded_bytes: number }>(
    `/storage/admin/large-share/${uploadId}/parts/${partNumber}`,
    form,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300_000,
    },
  )
  return data
}

export async function completeAdminLargeShare(uploadId: number): Promise<LargeShareComplete> {
  const { data } = await http.post<LargeShareComplete>(
    `/storage/admin/large-share/${uploadId}/complete`,
    {},
    { timeout: 300_000 },
  )
  return data
}

export async function abortAdminLargeShare(uploadId: number): Promise<void> {
  await http.post(`/storage/admin/large-share/${uploadId}/abort`)
}

export interface StorageReceiptItem {
  id: number
  supplier_inn: string
  supplier_name?: string | null
  period_code: string
  doc_kind: string
  is_correction?: boolean
  source_filename: string
  has_pdf: boolean
}

export interface StorageSalesBookItem {
  id: number
  seller_inn: string
  buyer_inn: string
  seller_name?: string | null
  buyer_name?: string | null
  source_filename: string
  has_pdf: boolean
}

export interface StorageSalesBookOrderGroup {
  order_id: number
  order_no: number
  lead_id: number
  buyer_inn: string
  buyer_name?: string | null
  items: StorageSalesBookItem[]
}

export interface StorageSalesBookUnitGroup {
  seller_inn: string
  seller_name: string
  orders: StorageSalesBookOrderGroup[]
}

export interface StorageReceiptPeriodGroup {
  period_code: string
  items: StorageReceiptItem[]
  sales_books?: StorageSalesBookItem[]
  sales_book_units?: StorageSalesBookUnitGroup[]
}

export async function listStorageReceiptsTree(): Promise<{
  periods: StorageReceiptPeriodGroup[]
}> {
  const { data } = await http.get<{ periods: StorageReceiptPeriodGroup[] }>(
    '/storage/receipts/tree',
  )
  return data
}

export async function downloadStorageReceipt(receiptId: number): Promise<Blob> {
  const { data } = await http.get<Blob>(`/storage/receipts/${receiptId}/download`, {
    responseType: 'blob',
  })
  return data
}

export async function downloadStorageSalesBook(extractId: number): Promise<Blob> {
  const { data } = await http.get<Blob>(`/storage/sales-books/${extractId}/download`, {
    responseType: 'blob',
  })
  return data
}
