import { ref } from 'vue'
import { describe, expect, it } from 'vitest'

import { useDashboardNavigation } from './useDashboardNavigation'

describe('useDashboardNavigation', () => {
  it('exposes the main Bot menu settings in the authenticated Dashboard', () => {
    const navigation = useDashboardNavigation(ref(['main_bot_menu']))

    expect(navigation.menuItems).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'main_bot_menu', label: '入口控制' }),
      ])
    )
    expect(navigation.currentTabTitle.value).toBe('入口控制')
  })

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
