import { computed, markRaw, type Component, type Ref } from 'vue'

import DashboardMonitorView from '../components/DashboardMonitorView.vue'
import GalleryCommentsTable from '../components/GalleryCommentsTable.vue'
import FinanceDashboard from '../components/FinanceDashboard.vue'
import GalleryTable from '../components/GalleryTable.vue'
import HistoryTable from '../components/HistoryTable.vue'
import HomeDashboard from '../components/HomeDashboard.vue'
import LogTable from '../components/LogTable.vue'
import RechargeSystem from '../components/RechargeSystem.vue'
import ReferralTable from '../components/ReferralTable.vue'
import TemplateManager from '../components/TemplateManager.vue'
import UserTable from '../components/UserTable.vue'
import WorkerHistoryTable from '../components/WorkerHistoryTable.vue'

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
}

const BASE_CONTAINER_CLASS = 'flex-1 flex flex-col min-h-0'
const PANEL_CONTAINER_CLASS =
  'flex-1 bg-white rounded-xl shadow-sm border p-6 flex flex-col min-h-0'

const TAB_COMPONENTS = {
  home: markRaw(HomeDashboard),
  finance: markRaw(FinanceDashboard),
  monitor: markRaw(DashboardMonitorView),
  users: markRaw(UserTable),
  history: markRaw(HistoryTable),
  worker_history: markRaw(WorkerHistoryTable),
  logs: markRaw(LogTable),
  recharge: markRaw(RechargeSystem),
  templates: markRaw(TemplateManager),
  gallery: markRaw(GalleryTable),
  gallery_comments: markRaw(GalleryCommentsTable),
  referrals: markRaw(ReferralTable),
} satisfies Record<string, Component>

export function useDashboardTabView(
  activeTab: Ref<string[]>,
  galleryComments: DashboardGalleryCommentsState,
  overview: DashboardOverviewState,
  userHistory: DashboardUserHistoryState
) {
  const tabViews = computed<Record<string, DashboardTabView>>(() => ({
    monitor: {
      component: TAB_COMPONENTS.monitor,
      containerClass: `${BASE_CONTAINER_CLASS} gap-6`,
      bindings: {},
    },
    home: {
      component: TAB_COMPONENTS.home,
      containerClass: BASE_CONTAINER_CLASS,
      bindings: {
        stats: overview.stats.value,
        statsHistory: overview.statsHistory.value,
        cumulativeStatsHistory: overview.cumulativeStatsHistory.value,
        historyTimeRange: overview.historyTimeRange.value,
        timeRangeOptions: overview.timeRangeOptions,
        'onUpdate:historyTimeRange': (value: number) => {
          overview.historyTimeRange.value = value
        },
        onLoadHistory: overview.loadHistory,
      },
    },
    finance: {
      component: TAB_COMPONENTS.finance,
      containerClass: BASE_CONTAINER_CLASS,
      bindings: {
        stats: overview.stats.value,
        statsHistory: overview.statsHistory.value,
        historyTimeRange: overview.historyTimeRange.value,
        timeRangeOptions: overview.timeRangeOptions,
        'onUpdate:historyTimeRange': (value: number) => {
          overview.historyTimeRange.value = value
        },
        onLoadHistory: overview.loadHistory,
      },
    },
    users: {
      component: TAB_COMPONENTS.users,
      containerClass: PANEL_CONTAINER_CLASS,
      bindings: {
        onViewHistory: userHistory.viewHistory,
      },
    },
    history: {
      component: TAB_COMPONENTS.history,
      containerClass: PANEL_CONTAINER_CLASS,
      bindings: {},
    },
    worker_history: {
      component: TAB_COMPONENTS.worker_history,
      containerClass: PANEL_CONTAINER_CLASS,
      bindings: {},
    },
    logs: {
      component: TAB_COMPONENTS.logs,
      containerClass: PANEL_CONTAINER_CLASS,
      bindings: {},
    },
    recharge: {
      component: TAB_COMPONENTS.recharge,
      containerClass: BASE_CONTAINER_CLASS,
      bindings: {},
    },
    templates: {
      component: TAB_COMPONENTS.templates,
      containerClass: PANEL_CONTAINER_CLASS,
      bindings: {},
    },
    gallery: {
      component: TAB_COMPONENTS.gallery,
      containerClass: PANEL_CONTAINER_CLASS,
      bindings: {
        onOpenCommentsTab: galleryComments.openCommentsTab,
      },
    },
    gallery_comments: {
      component: TAB_COMPONENTS.gallery_comments,
      containerClass: PANEL_CONTAINER_CLASS,
      bindings: {
        selectedPostId: galleryComments.selectedPostId.value,
      },
    },
    referrals: {
      component: TAB_COMPONENTS.referrals,
      containerClass: BASE_CONTAINER_CLASS,
      bindings: {},
    },
  }))

  const currentTabView = computed(() => {
    const activeKey = activeTab.value[0]
    return tabViews.value[activeKey] ?? tabViews.value.templates
  })

  return {
    currentTabView,
  }
}
