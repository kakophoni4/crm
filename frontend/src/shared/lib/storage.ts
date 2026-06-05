import { logger } from '@/shared/lib/logger'

export const storage = {
  get(key: string): string | null {
    try {
      return localStorage.getItem(key)
    } catch (err) {
      logger.warn('storage.get failed', key, err)
      return null
    }
  },

  set(key: string, value: string): void {
    try {
      localStorage.setItem(key, value)
    } catch (err) {
      logger.warn('storage.set failed', key, err)
    }
  },

  remove(key: string): void {
    try {
      localStorage.removeItem(key)
    } catch (err) {
      logger.warn('storage.remove failed', key, err)
    }
  },
}
