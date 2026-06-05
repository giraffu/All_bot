import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { nodePolyfills } from 'vite-plugin-node-polyfills'

const publicBase = process.env.PUBLIC_BASE || '/'

export default defineConfig({
  base: publicBase,
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return
          }

          if (id.includes('@tonconnect') || id.includes('@ton/core')) {
            return 'vendor-ton'
          }

          if (id.includes('react') || id.includes('react-dom')) {
            return 'vendor-react'
          }

          if (id.includes('@twa-dev')) {
            return 'vendor-twa'
          }

          if (id.includes('buffer')) {
            return 'vendor-polyfills'
          }
        },
      },
    },
  },
  plugins: [
    react(),
    nodePolyfills({
      include: ['buffer'],
    }),
  ],
  server: {
    host: true,
    port: 3399,
    strictPort: true,
    allowedHosts: ['pay.aivison.it.com', 'chuzeyu.cn'],
    hmr: {
      protocol: 'wss',
      clientPort: 443,
      path: publicBase,
    },
  },
})
