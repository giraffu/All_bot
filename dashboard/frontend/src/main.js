import { createApp } from 'vue'
import 'ant-design-vue/dist/reset.css'
import './style.css'
import App from './App.vue'
import { installAntDesign } from './plugins/antDesign'
import { startFrontendUpdateMonitor } from './releaseUpdateMonitor'

const app = createApp(App)
installAntDesign(app)
app.mount('#app')

startFrontendUpdateMonitor({
  currentEntryUrl: import.meta.url,
  origin: window.location.origin,
  fetchHtml: async () => {
    const response = await fetch(window.location.href, {
      cache: 'no-store',
      headers: { 'Cache-Control': 'no-cache' },
    })
    if (!response.ok) throw new Error(`dashboard entry check failed: ${response.status}`)
    return response.text()
  },
  reload: () => window.location.reload(),
})
