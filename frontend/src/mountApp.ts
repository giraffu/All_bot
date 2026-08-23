import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import '../../shared/web/theme-tokens.css'
import App from './App.vue'
import router from './router'
import i18n from './i18n'
import { useThemeStore } from './stores/theme'

const CHUNK_RELOAD_MARKER_KEY = '__allbot_chunk_reload_marker__'
const dynamicImportErrorPatterns = [
  /Failed to fetch dynamically imported module/i,
  /Importing a module script failed/i,
  /error loading dynamically imported module/i,
  /ChunkLoadError/i,
]

const isDynamicImportError = (error: unknown) => {
  const message = error instanceof Error
    ? error.message
    : typeof error === 'string'
      ? error
      : ''

  return dynamicImportErrorPatterns.some((pattern) => pattern.test(message))
}

const reloadCurrentPageOnce = () => {
  if (typeof window === 'undefined') {
    return false
  }

  const currentPath = window.location.pathname + window.location.search + window.location.hash
  const reloadedPath = window.sessionStorage.getItem(CHUNK_RELOAD_MARKER_KEY)

  if (reloadedPath === currentPath) {
    return false
  }

  window.sessionStorage.setItem(CHUNK_RELOAD_MARKER_KEY, currentPath)
  window.location.reload()
  return true
}

export const mountApp = () => {
  router.afterEach(() => {
    if (typeof window === 'undefined') {
      return
    }

    window.sessionStorage.removeItem(CHUNK_RELOAD_MARKER_KEY)
  })

  router.onError((error) => {
    if (isDynamicImportError(error) && reloadCurrentPageOnce()) {
      return
    }

    console.error(error)
  })

  if (typeof window !== 'undefined') {
    window.addEventListener('vite:preloadError', (event) => {
      if (reloadCurrentPageOnce()) {
        event.preventDefault()
      }
    })
  }

  const app = createApp(App)
  const pinia = createPinia()
  const themeStore = useThemeStore(pinia)

  themeStore.initTheme()

  app.use(pinia)
  app.use(router)
  app.use(i18n)

  app.mount('#app')
}
