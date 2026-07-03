import { ref } from 'vue'
import { describe, expect, it } from 'vitest'

import { useDashboardNavigation } from './useDashboardNavigation'

describe('useDashboardNavigation', () => {
  it('keeps QQCC lazy bot settings out of the main dashboard shell', () => {
    const activeTab = ref(['qqcc_bot'])
    const navigation = useDashboardNavigation(activeTab)

    expect(navigation.menuItems).not.toEqual(
      expect.arrayContaining([expect.objectContaining({ key: 'qqcc_bot' })])
    )
    expect(navigation.scrollableTabKeys).not.toContain('qqcc_bot')
    expect(navigation.currentTabTitle.value).toBe('模板共建')
  })
})
