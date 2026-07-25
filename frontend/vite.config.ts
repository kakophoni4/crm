import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
/// <reference types="vitest/config" />
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          if (id.includes('naive-ui')) return 'vendor-naive-ui'
          if (
            id.includes('vue-router') ||
            id.includes('/pinia/') ||
            id.includes('\\pinia\\') ||
            id.includes('@vue/') ||
            /[/\\]vue[/\\]/.test(id)
          ) {
            return 'vendor-vue'
          }
          if (id.includes('@sentry')) return 'vendor-sentry'
          if (id.includes('axios')) return 'vendor-axios'
          if (id.includes('@vueuse')) return 'vendor-vueuse'
          if (id.includes('date-fns')) return 'vendor-date-fns'
          if (id.includes('lucide-vue-next')) return 'vendor-icons'
          if (id.includes('sip.js')) return 'vendor-sip'
          if (id.includes('xlsx')) return 'vendor-xlsx'
          if (id.includes('mammoth')) return 'vendor-mammoth'
        },
      },
    },
  },
  server: {
    port: 5173,
  },
  test: {
    environment: 'happy-dom',
    globals: true,
    include: ['tests/**/*.spec.ts'],
    setupFiles: ['tests/setup/sentry-mock.ts', 'tests/setup/group-directory-mock.ts'],
  },
})
