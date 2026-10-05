export const DEVICE_LIMIT_OPTIONS = [3, 4, 5, 6, 7, 8].map(value => ({
  value, label: `${value} IP-подключений`,
}))
export interface ConnectionSlot { ip: string; connected_at: number; nodes: string }
export interface IssuanceEligibility { can_create: boolean; trial_available: boolean; trial_used: boolean; current_subscription_id: string | null }
