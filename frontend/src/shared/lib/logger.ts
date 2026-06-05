import { env } from '@/shared/config/env'

const debugEnabled =
  env.VITE_LOG_DEBUG === 'true' || import.meta.env.DEV

type LogFn = (...args: unknown[]) => void

function wrap(level: 'debug' | 'info' | 'warn' | 'error', fn: LogFn): LogFn {
  return (...args: unknown[]) => {
    if (level === 'debug' && !debugEnabled) return
    fn(`[crm]`, ...args)
  }
}

export const logger = {
  debug: wrap('debug', console.debug.bind(console)),
  info: wrap('info', console.info.bind(console)),
  warn: wrap('warn', console.warn.bind(console)),
  error: wrap('error', console.error.bind(console)),
}
