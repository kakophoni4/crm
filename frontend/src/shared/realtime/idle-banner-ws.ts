import { getRealtimeWS } from '@/shared/realtime/ws-client'

type SettingsHandler = (enabled: boolean) => void
type ShowHandler = () => void

let connected = false

export async function connectIdleBannerRealtime(
  onSettings: SettingsHandler,
  onShow: ShowHandler,
): Promise<void> {
  const ws = getRealtimeWS()
  ws.onTopic('idle.banner.settings', (payload) => {
    onSettings(Boolean(payload.is_enabled))
  })
  ws.onTopic('idle.banner.show', () => {
    onShow()
  })
  if (!connected) {
    await ws.connect()
    connected = true
  }
}
