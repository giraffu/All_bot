import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useThemeStore } from './theme'

describe('avatar theme store', () => {
  beforeEach(() => {
    localStorage.clear()
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: true,
        addEventListener: vi.fn(),
      })),
    })
    setActivePinia(createPinia())
  })

  it('shares the main web preference key and applies the resolved theme', () => {
    const theme = useThemeStore()

    theme.init()
    theme.setTheme('light')

    expect(localStorage.getItem('allbot_theme_preference')).toBe('light')
    expect(document.documentElement.dataset.theme).toBe('light')
  })
})
