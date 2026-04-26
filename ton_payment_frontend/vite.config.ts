import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { nodePolyfills } from 'vite-plugin-node-polyfills'

const publicBase = process.env.PUBLIC_BASE || '/'

export default defineConfig({
  base: publicBase,
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
