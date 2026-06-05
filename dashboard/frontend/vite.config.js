import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return
          }

          if (id.includes('echarts') || id.includes('zrender')) {
            return 'vendor-charts'
          }

          if (id.includes('ant-design-vue') || id.includes('@ant-design')) {
            return 'vendor-ant'
          }

          if (id.includes('/vue/') || id.includes('vue-echarts')) {
            return 'vendor-vue'
          }

          if (id.includes('axios')) {
            return 'vendor-http'
          }
        },
      },
    },
  },
})
