import { ref } from 'vue'
import { describe, expect, it } from 'vitest'

import { useDashboardNavigation } from './useDashboardNavigation'

describe('useDashboardNavigation', () => {
  it('includes the QQCC lazy bot settings tab', () => {
    const activeTab = ref(['qqcc_bot'])
    const navigation = useDashboardNavigation(activeTab)

    expect(navigation.menuItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          key: 'qqcc_bot',
          label: '懒人Bot配置',
        }),
      ])
    )
    expect(navigation.scrollableTabKeys).toContain('qqcc_bot')
    expect(navigation.currentTabTitle.value).toBe('懒人Bot配置')
  })
})
