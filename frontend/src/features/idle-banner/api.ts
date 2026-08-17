import { http } from '@/shared/api/http'

export async function getIdleBannerStatus(): Promise<{ is_enabled: boolean }> {
  const { data } = await http.get<{ is_enabled: boolean }>('/idle-banner')
  return data
}

export async function patchIdleBanner(isEnabled: boolean): Promise<{ is_enabled: boolean }> {
  const { data } = await http.patch<{ is_enabled: boolean }>('/idle-banner', {
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
