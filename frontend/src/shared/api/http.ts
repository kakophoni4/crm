import axios, {
  type AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios'
import { ulid } from 'ulid'

import { env } from '@/shared/config/env'

/** API error envelope — docs/API_CONTRACT.md §1.2 */
export interface ApiErrorPayload {
  code: string
  message: string
  details?: Record<string, unknown>
  request_id?: string
}

export interface ApiErrorBody {
  error: ApiErrorPayload
}

export class AppError extends Error {
  readonly code: string
  readonly details?: Record<string, unknown>
  readonly requestId?: string
  readonly status?: number

  constructor(payload: ApiErrorPayload, status?: number) {
    super(payload.message)
    this.name = 'AppError'
    this.code = payload.code
    this.details = payload.details
    this.requestId = payload.request_id
    this.status = status
  }
}

function isApiErrorBody(data: unknown): data is ApiErrorBody {
  if (!data || typeof data !== 'object') return false
  const err = (data as ApiErrorBody).error
  return (
    !!err &&
    typeof err === 'object' &&
    typeof err.code === 'string' &&
    typeof err.message === 'string'
  )
}

export function parseAppError(error: AxiosError): AppError {
  const status = error.response?.status
  const data = error.response?.data

  if (isApiErrorBody(data)) {
    return new AppError(data.error, status)
  }

  return new AppError(
    {
      code: 'internal_error',
      message: error.message || 'Network error',
      request_id: error.config?.headers?.['X-Request-Id'] as string | undefined,
    },
    status,
  )
}

function attachRequestId(config: InternalAxiosRequestConfig): InternalAxiosRequestConfig {
  config.headers = config.headers ?? {}
  if (!config.headers['X-Request-Id']) {
    config.headers['X-Request-Id'] = ulid()
  }
  return config
}

export function createHttpClient(mapErrors = true): AxiosInstance {
  const client = axios.create({
    baseURL: env.VITE_API_BASE_URL,
    timeout: 15_000,
    headers: {
      'Content-Type': 'application/json',
    },
  })

  client.interceptors.request.use(attachRequestId)
  if (mapErrors) {
    installApiErrorInterceptor(client)
  }

  return client
}

export function installApiErrorInterceptor(client: AxiosInstance = http): void {
  client.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => Promise.reject(parseAppError(error)),
  )
}

/** Shared client — error mapping installed after auth refresh in `setupAuthHttpInterceptors`. */
export const http = createHttpClient(false)
