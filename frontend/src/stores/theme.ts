import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export type ThemePreference = 'system' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

const THEME_STORAGE_KEY = 'allbot_theme_preference'
const SYSTEM_DARK_MEDIA_QUERY = '(prefers-color-scheme: dark)'

const isThemePreference = (value: string | null): value is ThemePreference =>
  value === 'system' || value === 'light' || value === 'dark'

const readStoredThemePreference = (): ThemePreference => {
  if (typeof window === 'undefined') {
    return 'system'
  }

  const storedValue = window.localStorage.getItem(THEME_STORAGE_KEY)
  return isThemePreference(storedValue) ? storedValue : 'system'
}

export const useThemeStore = defineStore('theme', () => {
  const selectedTheme = ref<ThemePreference>(readStoredThemePreference())
  const systemTheme = ref<ResolvedTheme>('dark')
  const initialized = ref(false)

  let mediaQueryList: MediaQueryList | null = null
  let mediaQueryListener: ((event: MediaQueryListEvent) => void) | null = null

  const resolvedTheme = computed<ResolvedTheme>(() =>
    selectedTheme.value === 'system' ? systemTheme.value : selectedTheme.value
  )

  const syncColorSchemeMeta = (resolved: ResolvedTheme) => {
    if (typeof document === 'undefined') {
      return
    }

    const meta = document.querySelector<HTMLMetaElement>('meta[name="color-scheme"]')
    const colorSchemeContent = resolved === 'light' ? 'only light' : 'dark'

    if (meta) {
      meta.setAttribute('content', colorSchemeContent)
    }
  }

  const applyThemeToDocument = () => {
    if (typeof document === 'undefined') {
      return
    }

    const resolved = resolvedTheme.value
    const root = document.documentElement
    const body = document.body
    const colorSchemeValue = resolved === 'light' ? 'only light' : 'dark'

    root.dataset.theme = resolved
    root.dataset.themePreference = selectedTheme.value
    root.style.colorScheme = colorSchemeValue

    if (body) {
      body.dataset.theme = resolved
      body.style.colorScheme = colorSchemeValue
    }

    syncColorSchemeMeta(resolved)
  }

  const updateSystemTheme = () => {
    if (typeof window === 'undefined') {
      return
    }

    systemTheme.value = window.matchMedia(SYSTEM_DARK_MEDIA_QUERY).matches ? 'dark' : 'light'
  }

  const attachSystemThemeListener = () => {
    if (typeof window === 'undefined' || mediaQueryListener) {
      return
    }

    mediaQueryList = window.matchMedia(SYSTEM_DARK_MEDIA_QUERY)
    updateSystemTheme()

    mediaQueryListener = (event: MediaQueryListEvent) => {
      systemTheme.value = event.matches ? 'dark' : 'light'
      if (selectedTheme.value === 'system') {
        applyThemeToDocument()
      }
    }

    if (typeof mediaQueryList.addEventListener === 'function') {
      mediaQueryList.addEventListener('change', mediaQueryListener)
      return
    }

    mediaQueryList.addListener(mediaQueryListener)
  }

  const persistSelectedTheme = () => {
    if (typeof window === 'undefined') {
      return
    }

    window.localStorage.setItem(THEME_STORAGE_KEY, selectedTheme.value)
  }

  const setTheme = (theme: ThemePreference) => {
    selectedTheme.value = theme
    persistSelectedTheme()
    applyThemeToDocument()
  }

  const initTheme = () => {
    if (typeof window === 'undefined') {
      return
    }

    selectedTheme.value = readStoredThemePreference()
    attachSystemThemeListener()
    persistSelectedTheme()
    applyThemeToDocument()
    initialized.value = true
  }

  return {
    selectedTheme,
    systemTheme,
    resolvedTheme,
    initialized,
    initTheme,
    setTheme,
  }
})
