import { http } from '@/shared/api/http'

export interface IdleBannerStatus {
  is_enabled: boolean
  has_image: boolean
  image_version: number
}

const DEFAULT_BANNER = '/idle-contract-banner.png'

export async function getIdleBannerStatus(): Promise<IdleBannerStatus> {
  const { data } = await http.get<IdleBannerStatus>('/idle-banner')
  return data
}

export async function patchIdleBanner(isEnabled: boolean): Promise<IdleBannerStatus> {
  const { data } = await http.patch<IdleBannerStatus>('/idle-banner', {
    is_enabled: isEnabled,
  })
  return data
}

export async function sendIdleBanner(userIds: number[]): Promise<{ sent: number }> {
  const { data } = await http.post<{ sent: number }>('/idle-banner/send', {
    user_ids: userIds,
  })
  return data
}

export async function uploadIdleBannerImage(file: File): Promise<IdleBannerStatus> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await http.post<IdleBannerStatus>('/idle-banner/image', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120_000,
  })
  return data
}

export async function fetchIdleBannerImageUrl(hasImage: boolean): Promise<string> {
  if (!hasImage) return DEFAULT_BANNER
  try {
    const { data } = await http.get<Blob>('/idle-banner/image', { responseType: 'blob' })
    if (!(data instanceof Blob) || data.size === 0 || data.type.includes('json')) {
      return DEFAULT_BANNER
    }
    return URL.createObjectURL(data)
  } catch {
    return DEFAULT_BANNER
  }
}
