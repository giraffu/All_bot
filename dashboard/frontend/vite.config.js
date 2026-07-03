import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'node:path'

const normalizeModuleId = (id) => id.replaceAll('\\', '/')

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        qqccConfig: resolve(__dirname, 'index.qqcc-config.html'),
      },
      output: {
        manualChunks(id) {
          const normalizedId = normalizeModuleId(id)
          if (!normalizedId.includes('node_modules')) {
            return
          }

          if (normalizedId.includes('/zrender/')) {
            return 'vendor-zrender'
          }

          if (normalizedId.includes('/echarts/') || normalizedId.includes('/vue-echarts/')) {
            return 'vendor-echarts'
          }

          if (normalizedId.includes('/vue/')) {
            return 'vendor-vue'
          }

          if (normalizedId.includes('axios')) {
            return 'vendor-http'
          }
        },
      },
    },
  },
})
