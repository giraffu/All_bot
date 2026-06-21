import { computed, defineAsyncComponent, markRaw, type Component, type Ref } from 'vue'

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

const BASE_CONTAINER_CLASS = 'flex-1 flex flex-col min-h-0'
const PANEL_CONTAINER_CLASS =
  'flex-1 bg-white rounded-xl shadow-sm border p-6 flex flex-col min-h-0'

const TAB_COMPONENTS = {
  home: markRaw(defineAsyncComponent(() => import('../components/HomeDashboard.vue'))),
  finance: markRaw(defineAsyncComponent(() => import('../components/FinanceDashboard.vue'))),
  monitor: markRaw(defineAsyncComponent(() => import('../components/DashboardMonitorView.vue'))),
  users: markRaw(defineAsyncComponent(() => import('../components/UserTable.vue'))),
  history: markRaw(defineAsyncComponent(() => import('../components/HistoryTable.vue'))),
  worker_history: markRaw(defineAsyncComponent(() => import('../components/WorkerHistoryTable.vue'))),
  logs: markRaw(defineAsyncComponent(() => import('../components/LogTable.vue'))),
  paid_group_guard: markRaw(
    defineAsyncComponent(() => import('../components/PaidGroupGuardSettings.vue'))
  ),
  recharge: markRaw(defineAsyncComponent(() => import('../components/RechargeSystem.vue'))),
  templates: markRaw(defineAsyncComponent(() => import('../components/TemplateManager.vue'))),
  gallery: markRaw(defineAsyncComponent(() => import('../components/GalleryTable.vue'))),
  gallery_comments: markRaw(
    defineAsyncComponent(() => import('../components/GalleryCommentsTable.vue'))
  ),
  referrals: markRaw(defineAsyncComponent(() => import('../components/ReferralTable.vue'))),
  site_notice: markRaw(defineAsyncComponent(() => import('../components/SiteNoticeSettings.vue'))),
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
        onViewFavorites: userHistory.viewFavorites,
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
    paid_group_guard: {
      component: TAB_COMPONENTS.paid_group_guard,
      containerClass: BASE_CONTAINER_CLASS,
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
    site_notice: {
      component: TAB_COMPONENTS.site_notice,
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
