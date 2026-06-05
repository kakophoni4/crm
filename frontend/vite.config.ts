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
