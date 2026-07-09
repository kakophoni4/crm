import { http } from '@/shared/api/http'

import type {
  AnonymousShareResult,
  GroupChatFileGroupSummary,
  GroupChatFileList,
  PublicShareInfo,
  ShareLink,
  ShareLinkCreateBody,
  VaultFile,
  VaultFileContent,
  VaultFileList,
} from './types'

export type {
  AnonymousShareResult,
  GroupChatFile,
  GroupChatFileGroupSummary,
  GroupChatFileList,
  PublicShareInfo,
  ShareLink,
  ShareLinkCreateBody,
  VaultFile,
  VaultFileContent,
  VaultFileList,
} from './types'

export async function listVaultFiles(params?: {
  offset?: number
  limit?: number
}): Promise<VaultFileList> {
  const { data } = await http.get<VaultFileList>('/storage/vault', { params })
  return data
}

export async function uploadVaultFile(file: File): Promise<VaultFile> {
  const form = new FormData()
  form.append('file', file)
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
  const { data } = await http.post<ShareLink>(`/storage/vault/${fileId}/shares`, body)
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
