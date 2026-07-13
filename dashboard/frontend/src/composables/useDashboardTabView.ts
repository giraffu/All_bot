import { computed, type Component, type Ref } from 'vue'
import {
  dashboardTabMap,
  defaultDashboardTabKey,
  type DashboardTabKey,
} from '../config/dashboardTabs'

type DashboardBindings = Record<string, unknown>

interface DashboardTabView {
  component: Component
  containerClass: string
  bindings: DashboardBindings
}

interface DashboardOverviewState {
  stats: Ref<unknown>
  statsHistory: Ref<unknown[]>
  cumulativeStatsHistory: Ref<unknown[]>
  historyTimeRange: Ref<number>
  timeRangeOptions: unknown[]
  loadHistory: () => Promise<void> | void
}

interface DashboardGalleryCommentsState {
  selectedPostId: Ref<number | undefined>
  openCommentsTab: (postId?: number) => void
}

interface DashboardUserHistoryState {
  viewHistory: (user: unknown) => void
  viewFavorites: (user: unknown) => void
}

export function useDashboardTabView(
  activeTab: Ref<string[]>,
  galleryComments: DashboardGalleryCommentsState,
  overview: DashboardOverviewState,
  userHistory: DashboardUserHistoryState
) {
  const buildOverviewBindings = () => ({
    stats: overview.stats.value,
    statsHistory: overview.statsHistory.value,
    cumulativeStatsHistory: overview.cumulativeStatsHistory.value,
    historyTimeRange: overview.historyTimeRange.value,
    timeRangeOptions: overview.timeRangeOptions,
    'onUpdate:historyTimeRange': (value: number) => {
      overview.historyTimeRange.value = value
    },
    onLoadHistory: overview.loadHistory,
  })

  const resolveBindings = (key: DashboardTabKey): DashboardBindings => {
    if (key === 'home') {
      return buildOverviewBindings()
    }
    if (key === 'finance') {
      return {
        stats: overview.stats.value,
        statsHistory: overview.statsHistory.value,
        historyTimeRange: overview.historyTimeRange.value,
        timeRangeOptions: overview.timeRangeOptions,
        'onUpdate:historyTimeRange': (value: number) => {
          overview.historyTimeRange.value = value
        },
        onLoadHistory: overview.loadHistory,
      }
    }
    if (key === 'users') {
      return {
        onViewHistory: userHistory.viewHistory,
        onViewFavorites: userHistory.viewFavorites,
      }
    }
    if (key === 'gallery') {
      return {
        onOpenCommentsTab: galleryComments.openCommentsTab,
      }
    }
    if (key === 'gallery_comments') {
      return {
        selectedPostId: galleryComments.selectedPostId.value,
      }
    }
    return {}
  }

  const currentTabView = computed(() => {
    const activeKey = activeTab.value[0] as DashboardTabKey
    const tab = dashboardTabMap[activeKey] ?? dashboardTabMap[defaultDashboardTabKey]
    return {
      component: tab.component,
      containerClass: tab.containerClass,
      bindings: resolveBindings(tab.key),
    } satisfies DashboardTabView
  })

  return {
    currentTabView,
  }
}
