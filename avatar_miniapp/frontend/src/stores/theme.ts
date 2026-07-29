import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export type ThemePreference = 'system' | 'light' | 'dark'

export const useThemeStore = defineStore('avatar-theme', () => {
  const selected = ref<ThemePreference>(
    (localStorage.getItem('allbot_theme_preference') as ThemePreference | null) || 'system',
  )
  const systemDark = ref(matchMedia('(prefers-color-scheme: dark)').matches)
  const resolved = computed(() =>
    selected.value === 'system' ? (systemDark.value ? 'dark' : 'light') : selected.value,
  )

  function apply() {
    document.documentElement.dataset.theme = resolved.value
    document.body.dataset.theme = resolved.value
  }

  function setTheme(value: ThemePreference) {
    selected.value = value
    localStorage.setItem('allbot_theme_preference', value)
    apply()
  }

  function init() {
    apply()
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (event) => {
      systemDark.value = event.matches
      if (selected.value === 'system') apply()
    })
  }

  return { selected, resolved, setTheme, init }
})
