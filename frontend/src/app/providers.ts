import { createPinia } from 'pinia'
import type { App } from 'vue'

import { router } from '@/app/router'
import { setupAuthHttpInterceptors, useAuthStore } from '@/shared/store/auth'
import { connectChatsRealtime } from '@/shared/realtime/chats-ws'
import { connectContactsRealtime } from '@/shared/realtime/contacts-ws'

export function setupProviders(app: App): void {
  const pinia = createPinia()
  app.use(pinia)
  setupAuthHttpInterceptors()
  app.use(router)

  void (async () => {
    await useAuthStore().hydrate()
    if (useAuthStore().isAuthenticated) {
      await connectContactsRealtime()
      await connectChatsRealtime()
    }
  })()
}
