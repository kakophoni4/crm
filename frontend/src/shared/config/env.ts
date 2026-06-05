function readEnv(): ImportMetaEnv {
  const env = import.meta.env
  if (!env.VITE_API_BASE_URL) {
    console.warn('[crm] VITE_API_BASE_URL is not set; using empty base URL')
  }
  return env
}

export const env = readEnv()
