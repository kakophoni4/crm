export function baseUrl(): string {
  return (process.env.BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')
}

/** API prefix; set API_BASE_URL on staging when app and API hosts differ. */
export function apiBaseUrl(): string {
  const explicit = process.env.API_BASE_URL?.replace(/\/$/, '')
  if (explicit) return explicit

  const app = baseUrl()
  try {
    const u = new URL(app)
    if (u.port === '5173') {
      return 'http://localhost:8000/api/v1'
    }
  } catch {
    /* fall through */
  }
  return `${app}/api/v1`
}

export interface Credentials {
  email: string
  password: string
}

export function operatorCredentials(): Credentials | null {
  const email = process.env.E2E_OPERATOR_A_EMAIL ?? process.env.E2E_EMAIL
  const password = process.env.E2E_OPERATOR_A_PASSWORD ?? process.env.E2E_PASSWORD
  if (!email || !password) return null
  return { email, password }
}

export function operatorBCredentials(): Credentials | null {
  const email = process.env.E2E_OPERATOR_B_EMAIL
  const password = process.env.E2E_OPERATOR_B_PASSWORD
  if (!email || !password) return null
  return { email, password }
}

export function seniorCredentials(): Credentials | null {
  const email = process.env.E2E_SENIOR_EMAIL
  const password = process.env.E2E_SENIOR_PASSWORD
  if (!email || !password) return null
  return { email, password }
}

export function botCredentials(): { code: string; secret: string } | null {
  const code = process.env.E2E_BOT_CODE
  const secret = process.env.E2E_BOT_SECRET
  if (!code || !secret) return null
  return { code, secret }
}

export function hasOperatorCredentials(): boolean {
  return operatorCredentials() != null
}
