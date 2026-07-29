import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5180,
    proxy: {
      '/api': {
        target: process.env.MINIAPP_API_PROXY || 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
})
