// @vitest-environment jsdom

import { effectScope, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { useMyFavoritesFilters } from './useMyFavoritesFilters'

describe('useMyFavoritesFilters', () => {
  it('hides and rejects the character library tab when production LTX is disabled', () => {
    const route = {
      query: { tab: 'characters' },
    } as any
    const router = {
      replace: vi.fn(),
    } as any
    const scope = effectScope()

    const filters = scope.run(() => useMyFavoritesFilters({
      route,
      router,
      allowedTypes: ref([]),
      isMobile: ref(true),
      t: (key: string) => key,
      clearBrowserState: vi.fn(),
      reloadPosts: vi.fn(),
    }))

    expect(filters?.filterTabs.value.map(tab => tab.id)).not.toContain('characters')
    expect(filters?.filterType.value).toBe('favorite')
    scope.stop()
  })
})
