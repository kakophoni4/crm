/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_WS_URL: string
  readonly VITE_SENTRY_DSN: string
  readonly VITE_SENTRY_ENVIRONMENT?: string
  readonly VITE_LOG_DEBUG: string
  readonly VITE_MAX_UPLOAD_BYTES?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
