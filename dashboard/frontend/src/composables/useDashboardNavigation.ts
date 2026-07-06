import { computed } from 'vue'
import { LogoutOutlined } from '@ant-design/icons-vue'
import {
  dashboardTabMap,
  dashboardTabs,
  defaultDashboardTabKey,
  scrollableDashboardTabKeys,
} from '../config/dashboardTabs'

export function useDashboardNavigation(activeTab: { value: string[] }) {
  const menuItems = dashboardTabs.map(({ key, label, icon }) => ({ key, label, icon }))

  const currentTabTitle = computed(() => {
    const activeKey = activeTab.value[0] as keyof typeof dashboardTabMap
    return dashboardTabMap[activeKey]?.label || dashboardTabMap[defaultDashboardTabKey].label
  })

  return {
    menuItems,
    scrollableTabKeys: scrollableDashboardTabKeys,
    currentTabTitle,
    logoutIcon: LogoutOutlined,
  }
}
