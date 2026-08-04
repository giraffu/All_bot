// @vitest-environment jsdom

import { defineComponent, nextTick } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const dashboardMocks = vi.hoisted(() => ({
  isAuthenticatedRef: null,
  clearAuthTokenMock: vi.fn(),
  refreshDataMock: vi.fn().mockResolvedValue(undefined),
  handleSearchMock: vi.fn(),
  closeSearchModalMock: vi.fn(),
  viewHistoryMock: vi.fn(),
  closeModalMock: vi.fn(),
  viewFavoritesMock: vi.fn(),
  closeFavoritesModalMock: vi.fn(),
  changeFavoritesPageMock: vi.fn(),
  loadHistoryMock: vi.fn(),
  routeTitleMap: {
    home: '数据大盘',
    finance: '充值数据',
    users: '用户管理',
  },
}))

const LoginStub = defineComponent({
  name: 'LoginStub',
  template: '<div class="login-stub">login</div>',
})

const DashboardSidebarStub = defineComponent({
  name: 'DashboardSidebarStub',
  props: ['collapsed', 'activeTab', 'menuItems'],
  emits: ['update:collapsed', 'update:activeTab', 'logout'],
  template: `
    <div class="dashboard-sidebar-stub" :data-collapsed="String(collapsed)">
      <button class="to-finance" @click="$emit('update:activeTab', ['finance'])">finance</button>
      <button class="to-users" @click="$emit('update:activeTab', ['users'])">users</button>
      <button class="sidebar-logout" @click="$emit('logout')">logout</button>
      <slot />
    </div>
  `,
})

const DashboardHeaderBarStub = defineComponent({
  name: 'DashboardHeaderBarStub',
  props: ['collapsed', 'searchQuery', 'currentTabTitle', 'refreshLoading'],
  emits: ['update:collapsed', 'update:searchQuery', 'search', 'refresh', 'logout'],
  template: `
    <div class="dashboard-header-bar-stub" :data-title="currentTabTitle" :data-loading="String(refreshLoading)">
      <button class="header-refresh" @click="$emit('refresh')">refresh</button>
      <button class="header-logout" @click="$emit('logout')">logout</button>
      <button class="header-search" @click="$emit('search')">search</button>
      <button class="header-query" @click="$emit('update:searchQuery', 'task-42')">query</button>
      <button class="header-toggle" @click="$emit('update:collapsed', !collapsed)">toggle</button>
    </div>
  `,
})

const HistoryModalStub = defineComponent({
  name: 'HistoryModalStub',
  props: ['show', 'user', 'history', 'loading'],
  emits: ['close'],
  template: '<div class="history-modal-stub" :data-open="String(show)" />',
})

const UserFavoritesModalStub = defineComponent({
  name: 'UserFavoritesModalStub',
  props: ['show', 'user', 'items', 'loading', 'page', 'pageSize', 'total'],
  emits: ['close', 'pageChange'],
  template: '<div class="favorites-modal-stub" :data-open="String(show)" />',
})

const DashboardTaskSearchModalStub = defineComponent({
  name: 'DashboardTaskSearchModalStub',
  props: ['visible', 'searchResult'],
  emits: ['update:visible', 'close'],
  template: '<div class="task-search-modal-stub" :data-open="String(visible)" />',
})

const CurrentTabStub = defineComponent({
  name: 'CurrentTabStub',
  props: ['activeKey'],
  template: '<div class="current-tab-stub">{{ activeKey }}</div>',
})

vi.mock('./components/Login.vue', () => ({
  default: LoginStub,
}))

vi.mock('./components/DashboardSidebar.vue', () => ({
  default: DashboardSidebarStub,
}))

vi.mock('./components/DashboardHeaderBar.vue', () => ({
  default: DashboardHeaderBarStub,
}))

vi.mock('./components/HistoryModal.vue', () => ({
  default: HistoryModalStub,
}))

vi.mock('./components/UserFavoritesModal.vue', () => ({
  default: UserFavoritesModalStub,
}))

vi.mock('./components/DashboardTaskSearchModal.vue', () => ({
  default: DashboardTaskSearchModalStub,
}))

vi.mock('./composables/useDashboardAuth', async () => {
  const { ref } = await vi.importActual('vue')
  dashboardMocks.isAuthenticatedRef ??= ref(false)

  return {
    useDashboardAuth: () => ({
      isAuthenticated: dashboardMocks.isAuthenticatedRef,
      clearAuthToken: dashboardMocks.clearAuthTokenMock,
    }),
  }
})

vi.mock('./composables/useDashboardOverview', async () => {
  const { ref } = await vi.importActual('vue')

  return {
    useDashboardOverview: () => ({
      stats: ref({ total_users: 0 }),
      statsHistory: ref([]),
      cumulativeStatsHistory: ref([]),
      historyTimeRange: ref(7),
      refreshLoading: ref(false),
      timeRangeOptions: [],
      loadHistory: dashboardMocks.loadHistoryMock,
      refreshData: dashboardMocks.refreshDataMock,
    }),
  }
})

vi.mock('./composables/useDashboardTaskSearch', async () => {
  const { ref } = await vi.importActual('vue')

  return {
    useDashboardTaskSearch: () => ({
      searchQuery: ref(''),
      searchResult: ref(null),
      searchModalVisible: ref(false),
      searchLoading: ref(false),
      handleSearch: dashboardMocks.handleSearchMock,
      closeSearchModal: dashboardMocks.closeSearchModalMock,
      isImage: () => false,
      isVideo: () => false,
      getTaskImageUrl: () => '',
      getTaskVideoUrl: () => '',
      getStatusColor: () => 'default',
    }),
  }
})

vi.mock('./composables/useDashboardUserHistory', async () => {
  const { ref } = await vi.importActual('vue')

  return {
    useDashboardUserHistory: () => ({
      showModal: ref(false),
      selectedUser: ref(null),
      userHistory: ref([]),
      historyLoading: ref(false),
      viewHistory: dashboardMocks.viewHistoryMock,
      closeModal: dashboardMocks.closeModalMock,
    }),
  }
})

vi.mock('./composables/useDashboardUserFavorites', async () => {
  const { ref } = await vi.importActual('vue')

  return {
    useDashboardUserFavorites: () => ({
      showFavoritesModal: ref(false),
      selectedFavoritesUser: ref(null),
      favoriteItems: ref([]),
      favoritesLoading: ref(false),
      favoritesPage: ref(1),
      favoritesPages: ref(0),
      favoritesPageSize: ref(12),
      favoritesTotal: ref(0),
      viewFavorites: dashboardMocks.viewFavoritesMock,
      changeFavoritesPage: dashboardMocks.changeFavoritesPageMock,
      closeFavoritesModal: dashboardMocks.closeFavoritesModalMock,
    }),
  }
})

vi.mock('./composables/useDashboardNavigation', async () => {
  const { computed } = await vi.importActual('vue')

  return {
    useDashboardNavigation: (activeTab) => ({
      menuItems: [
        { key: 'home', label: '数据大盘' },
        { key: 'finance', label: '充值数据' },
        { key: 'users', label: '用户管理' },
      ],
      scrollableTabKeys: ['home', 'finance'],
      currentTabTitle: computed(
        () => dashboardMocks.routeTitleMap[activeTab.value[0]] ?? '模板共建'
      ),
      logoutIcon: {},
    }),
  }
})

vi.mock('./composables/useDashboardTabView', async () => {
  const { computed } = await vi.importActual('vue')

  return {
    useDashboardTabView: (activeTab) => ({
      currentTabView: computed(() => ({
        component: CurrentTabStub,
        containerClass: `container-${activeTab.value[0]}`,
        bindings: {
          activeKey: activeTab.value[0],
        },
      })),
    }),
  }
})

const App = await import('./App.vue').then(module => module.default)

const LayoutStub = defineComponent({
  name: 'ALayoutStub',
  template: '<div class="a-layout-stub"><slot /></div>',
})

const LayoutContentStub = defineComponent({
  name: 'ALayoutContentStub',
  props: ['class'],
  template: '<main class="a-layout-content-stub" :class="$props.class"><slot /></main>',
})

const mountApp = () =>
  mount(App, {
    global: {
      stubs: {
        'a-layout': LayoutStub,
        ALayout: LayoutStub,
        'a-layout-content': LayoutContentStub,
        ALayoutContent: LayoutContentStub,
      },
    },
  })

describe('Dashboard App', () => {
  beforeEach(() => {
    window.matchMedia = vi.fn().mockImplementation(query => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    dashboardMocks.isAuthenticatedRef.value = false
    dashboardMocks.clearAuthTokenMock.mockReset()
    dashboardMocks.refreshDataMock.mockReset()
    dashboardMocks.refreshDataMock.mockResolvedValue(undefined)
    dashboardMocks.handleSearchMock.mockReset()
    dashboardMocks.closeSearchModalMock.mockReset()
    dashboardMocks.viewHistoryMock.mockReset()
    dashboardMocks.closeModalMock.mockReset()
    dashboardMocks.viewFavoritesMock.mockReset()
    dashboardMocks.closeFavoritesModalMock.mockReset()
    dashboardMocks.changeFavoritesPageMock.mockReset()
    dashboardMocks.loadHistoryMock.mockReset()
  })

  it('renders the login screen when the dashboard is unauthenticated', () => {
    const wrapper = mountApp()

    expect(wrapper.find('.login-stub').exists()).toBe(true)
    expect(wrapper.find('.dashboard-sidebar-stub').exists()).toBe(false)
  })

  it('renders the dashboard shell and refreshes only for scrollable summary tabs', async () => {
    dashboardMocks.isAuthenticatedRef.value = true

    const wrapper = mountApp()
    await flushPromises()
    const initialRefreshCount = dashboardMocks.refreshDataMock.mock.calls.length

    expect(initialRefreshCount).toBeGreaterThanOrEqual(1)
    expect(wrapper.find('.dashboard-sidebar-stub').exists()).toBe(true)
    expect(wrapper.find('.dashboard-header-bar-stub').attributes('data-title')).toBe('数据大盘')
    expect(wrapper.find('.current-tab-stub').text()).toBe('home')
    expect(wrapper.find('.container-home').exists()).toBe(true)
    expect(wrapper.find('.a-layout-content-stub').classes()).toContain('overflow-y-auto')
    expect(wrapper.get('.dashboard-tab-viewport').classes()).toContain('min-h-0')

    await wrapper.get('.to-finance').trigger('click')
    await nextTick()
    await flushPromises()

    expect(dashboardMocks.refreshDataMock.mock.calls.length).toBe(initialRefreshCount + 1)
    expect(wrapper.find('.dashboard-header-bar-stub').attributes('data-title')).toBe('充值数据')
    expect(wrapper.find('.current-tab-stub').text()).toBe('finance')
    expect(wrapper.find('.container-finance').exists()).toBe(true)

    await wrapper.get('.to-users').trigger('click')
    await nextTick()
    await flushPromises()

    expect(dashboardMocks.refreshDataMock.mock.calls.length).toBe(initialRefreshCount + 1)
    expect(wrapper.find('.dashboard-header-bar-stub').attributes('data-title')).toBe('用户管理')
    expect(wrapper.find('.a-layout-content-stub').classes()).toContain('overflow-hidden')
  })

  it('forwards refresh, search and logout actions to the app orchestration layer', async () => {
    dashboardMocks.isAuthenticatedRef.value = true

    const wrapper = mountApp()
    await flushPromises()
    const initialRefreshCount = dashboardMocks.refreshDataMock.mock.calls.length

    await wrapper.get('.header-refresh').trigger('click')
    await wrapper.get('.header-search').trigger('click')
    await wrapper.get('.sidebar-logout').trigger('click')
    await wrapper.get('.header-logout').trigger('click')

    expect(dashboardMocks.refreshDataMock.mock.calls.length).toBe(initialRefreshCount + 1)
    expect(dashboardMocks.handleSearchMock).toHaveBeenCalledTimes(1)
    expect(dashboardMocks.clearAuthTokenMock).toHaveBeenCalledTimes(2)
  })

  it('uses an overlay sidebar that stays reachable and closes after mobile navigation', async () => {
    window.matchMedia = vi.fn().mockImplementation(query => ({
      matches: query === '(max-width: 767px)',
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    dashboardMocks.isAuthenticatedRef.value = true

    const wrapper = mountApp()
    await flushPromises()

    expect(wrapper.get('.dashboard-sidebar-stub').attributes('data-collapsed')).toBe('true')
    expect(wrapper.find('.dashboard-sidebar-backdrop').exists()).toBe(false)

    await wrapper.get('.header-toggle').trigger('click')
    await nextTick()

    expect(wrapper.get('.dashboard-sidebar-stub').attributes('data-collapsed')).toBe('false')
    expect(wrapper.find('.dashboard-sidebar-backdrop').exists()).toBe(true)

    await wrapper.get('.dashboard-sidebar-backdrop').trigger('click')
    await nextTick()

    expect(wrapper.get('.dashboard-sidebar-stub').attributes('data-collapsed')).toBe('true')

    await wrapper.get('.header-toggle').trigger('click')
    await nextTick()

    await wrapper.get('.to-users').trigger('click')
    await nextTick()

    expect(wrapper.get('.dashboard-sidebar-stub').attributes('data-collapsed')).toBe('true')
    expect(wrapper.find('.dashboard-sidebar-backdrop').exists()).toBe(false)
  })
})
