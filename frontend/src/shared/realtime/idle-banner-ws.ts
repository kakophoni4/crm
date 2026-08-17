import { getRealtimeWS } from '@/shared/realtime/ws-client'

export interface IdleBannerSettingsPayload {
  is_enabled: boolean
  has_image?: boolean
  image_version?: number
}

type SettingsHandler = (payload: IdleBannerSettingsPayload) => void
type ShowHandler = () => void

let connected = false

export async function connectIdleBannerRealtime(
  onSettings: SettingsHandler,
  onShow: ShowHandler,
): Promise<void> {
  const ws = getRealtimeWS()
  ws.onTopic('idle.banner.settings', (payload) => {
    onSettings({
      is_enabled: Boolean(payload.is_enabled),
      has_image: Boolean(payload.has_image),
      image_version: Number(payload.image_version || 0),
    })
  })
  ws.onTopic('idle.banner.show', () => {
    onShow()
  })
  if (!connected) {
    await ws.connect()
    connected = true
  }
}
