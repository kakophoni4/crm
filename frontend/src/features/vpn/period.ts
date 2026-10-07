export const subscriptionPeriods = [7, 14, 21, 30, 90]
export const trialPeriods = [1, 2, 3, 7]
export const subscriptionKindLabels: Record<string, string> = { gift: 'Подарок', purchase: 'Покупка', trial: 'Пробный период' }

export function validPeriod(value: number | null | undefined): value is number {
  return value != null && Number.isInteger(value) && value >= 1 && value <= 3650
}

export function periodEnd(days: number, expiresAt = 0, now = Date.now() / 1000): number {
  return Math.max(now, expiresAt) + days * 86400
}

export function vpnDeliveryText(value: { kind: string; expires_at: number; happ_url: string; clash_url: string; v2rayng_url: string; guide_url: string; ghostlane_url?: string }): string {
  const title = value.kind === 'trial' ? 'Ваш пробный VPN' : value.kind === 'gift' ? 'Ваш VPN в подарок' : 'Ваша VPN-подписка'
  const end = new Date(value.expires_at * 1000).toLocaleString('ru-RU')
  const ghostlane = value.ghostlane_url || value.happ_url.replace('format=happ', 'format=ghostlane')
  return `${title} действует до ${end}.\n\nСкачать приложение и подключиться: ${value.guide_url}\n\nHapp: ${value.happ_url}\nGhostlane: ${ghostlane}\nKoala Clash / Clash Meta: ${value.clash_url}\nv2rayNG: ${value.v2rayng_url}`
}
