<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import Login from './components/Login.vue'
import HistoryModal from './components/HistoryModal.vue'
import UserFavoritesModal from './components/UserFavoritesModal.vue'
import DashboardSidebar from './components/DashboardSidebar.vue'
import DashboardHeaderBar from './components/DashboardHeaderBar.vue'
import DashboardTaskSearchModal from './components/DashboardTaskSearchModal.vue'
import { useDashboardAuth } from './composables/useDashboardAuth'
import { useDashboardOverview } from './composables/useDashboardOverview'
import { useDashboardTaskSearch } from './composables/useDashboardTaskSearch'
import { useDashboardUserHistory } from './composables/useDashboardUserHistory'
import { useDashboardUserFavorites } from './composables/useDashboardUserFavorites'
import { useDashboardNavigation } from './composables/useDashboardNavigation'
import { useDashboardTabView } from './composables/useDashboardTabView'
import type { DashboardTabKey } from './config/dashboardTabs'
import { useDashboardViewport } from './composables/useDashboardViewport'

const { isAuthenticated, clearAuthToken } = useDashboardAuth()
const activeTab = ref<string[]>(['home'])
const galleryCommentsPostId = ref<number | undefined>(undefined)
const { isMobile } = useDashboardViewport()
const collapsed = ref(isMobile.value)
const {
  stats,
  statsHistory,
  financeStats,
  financeStatsHistory,
  cumulativeStatsHistory,
  historyTimeRange,
  refreshLoading,
  timeRangeOptions,
  loadHistory,
  loadFinanceHistory,
  refreshData
} = useDashboardOverview()
const {
  searchQuery,
  searchResult,
  searchModalVisible,
  handleSearch,
  closeSearchModal,
  isImage,
  isVideo,
  getTaskImageUrl,
  getTaskVideoUrl,
  getStatusColor
} = useDashboardTaskSearch()
const {
  showModal,
  selectedUser,
  userHistory,
  historyLoading,
  historyPage,
  historyPageSize,
  historyTotal,
  viewHistory,
  changeHistoryPage,
  closeModal
} = useDashboardUserHistory()
const {
  showFavoritesModal,
  selectedFavoritesUser,
  favoriteItems,
  favoritesLoading,
  favoritesPage,
  favoritesPages,
  favoritesPageSize,
  favoritesTotal,
  viewFavorites,
  changeFavoritesPage,
  closeFavoritesModal,
} = useDashboardUserFavorites()
const openGalleryCommentsTab = (postId?: number) => {
  galleryCommentsPostId.value = typeof postId === 'number' ? postId : undefined
  activeTab.value = ['gallery_comments']
}

const { menuItems, scrollableTabKeys, currentTabTitle, logoutIcon } =
  useDashboardNavigation(activeTab)
const { currentTabView } = useDashboardTabView(
  activeTab,
  {
    selectedPostId: galleryCommentsPostId,
    openCommentsTab: openGalleryCommentsTab,
  },
  {
    stats,
    statsHistory,
    financeStats,
    financeStatsHistory,
    cumulativeStatsHistory,
    historyTimeRange,
    timeRangeOptions,
    loadHistory,
    loadFinanceHistory,
  },
  {
    viewHistory,
    viewFavorites,
  },
)

const isActiveTabScrollable = computed(() =>
  scrollableTabKeys.includes(activeTab.value[0] as DashboardTabKey)
)

// Auto refresh when switching tabs
watch(activeTab, (newTab) => {
  const tab = newTab[0]
  if (tab === 'home' || tab === 'finance') {
    void refreshData(tab)
  }
  if (isMobile.value) {
    collapsed.value = true
  }
  // UserTable, history, templates handle their own data fetching
})

watch(isMobile, (mobile) => {
  collapsed.value = mobile
})

watch(
  isAuthenticated,
  (authenticated) => {
    if (authenticated) {
      void refreshData(activeTab.value[0])
    }
  },
  { immediate: true }
)

const handleLogout = () => {
  clearAuthToken()
}

const refreshActiveTab = () => refreshData(activeTab.value[0])
</script>

<template>
  <Login v-if="!isAuthenticated" />
  
  <a-layout v-else class="dashboard-shell h-screen overflow-hidden">
    <dashboard-sidebar
      v-model:collapsed="collapsed"
      v-model:active-tab="activeTab"
      :menu-items="menuItems"
      :logout-icon="logoutIcon"
      :mobile="isMobile"
      @logout="handleLogout"
    />

    <button
      v-if="isMobile && !collapsed"
      type="button"
      class="dashboard-sidebar-backdrop"
      aria-label="关闭导航菜单"
      @click="collapsed = true"
    />

    <a-layout class="dashboard-main h-full min-h-0 min-w-0">
      <dashboard-header-bar
        v-model:collapsed="collapsed"
        v-model:search-query="searchQuery"
        :current-tab-title="currentTabTitle"
        :refresh-loading="refreshLoading"
        @search="handleSearch"
        @refresh="refreshActiveTab"
        @logout="handleLogout"
      />

      <!-- Content -->
      <a-layout-content 
        class="dashboard-content p-6 bg-gray-50 flex flex-col h-[calc(100vh-64px)]"
        :class="isActiveTabScrollable ? 'overflow-y-auto' : 'overflow-hidden'"
      >
        <div class="dashboard-tab-viewport w-full flex-1 flex flex-col min-h-0">
          <div :class="currentTabView.containerClass">
            <component :is="currentTabView.component" v-bind="currentTabView.bindings" />
          </div>
        </div>
      </a-layout-content>
    </a-layout>

    <!-- History Modal -->
    <HistoryModal 
      :show="showModal" 
      :user="selectedUser" 
      :history="userHistory" 
      :loading="historyLoading" 
      :page="historyPage"
      :page-size="historyPageSize"
      :total="historyTotal"
      @page-change="changeHistoryPage"
      @close="closeModal" 
    />

    <user-favorites-modal
      :show="showFavoritesModal"
      :user="selectedFavoritesUser"
      :items="favoriteItems"
      :loading="favoritesLoading"
      :page="favoritesPage"
      :pages="favoritesPages"
      :page-size="favoritesPageSize"
      :total="favoritesTotal"
      @close="closeFavoritesModal"
      @page-change="changeFavoritesPage"
    />

    <dashboard-task-search-modal
      v-model:visible="searchModalVisible"
      :search-result="searchResult"
      :is-image="isImage"
      :is-video="isVideo"
      :get-task-image-url="getTaskImageUrl"
      :get-task-video-url="getTaskVideoUrl"
      :get-status-color="getStatusColor"
      @close="closeSearchModal"
    />
  </a-layout>
</template>

<style>
.dashboard-shell {
  height: 100dvh;
}

/* Sidebar Styling */
.logo-container {
  height: 64px;
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  overflow: hidden;
  background: #001529;
}

.logo-icon {
  min-width: 32px;
  height: 32px;
  background: linear-gradient(135deg, #1890ff 0%, #0050b3 100%);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: bold;
  font-size: 18px;
  box-shadow: 0 4px 10px rgba(24, 144, 255, 0.3);
}

.logo-text {
  color: white;
  font-weight: 600;
  font-size: 18px;
  white-space: nowrap;
}

.sidebar-shadow {
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.15);
}

.sidebar-footer {
  position: absolute;
  bottom: 0;
  width: 100%;
  padding: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

/* Content Area Fixes */
.ant-layout-content {
  scrollbar-width: thin;
  scrollbar-color: #d1d5db transparent;
}

::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 10px;
}
::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}

/* Component Overrides */
.ant-layout-header {
  padding: 0 24px !important;
  background: #fff !important;
}

.ant-card {
  border-radius: 12px !important;
  border: 1px solid #f0f0f0 !important;
  transition: all 0.3s !important;
}

.ant-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05) !important;
}

.ant-table-wrapper {
  background: white;
  border-radius: 8px;
}

.dashboard-sidebar-backdrop {
  display: none;
}

@media (max-width: 767px) {
  .dashboard-shell,
  .dashboard-main {
    width: 100%;
    min-width: 0;
  }

  .dashboard-sidebar-backdrop {
    position: fixed;
    inset: 0;
    z-index: 45;
    display: block;
    border: 0;
    background: rgba(15, 23, 42, 0.48);
    -webkit-tap-highlight-color: transparent;
  }

  .dashboard-content.ant-layout-content {
    height: calc(100dvh - 56px);
    min-width: 0;
    padding: 12px !important;
  }

  .dashboard-tab-viewport,
  .dashboard-tab-viewport > div {
    width: 100%;
    min-width: 0;
  }

  .dashboard-panel {
    padding: 12px !important;
  }

  .ant-card-head {
    min-height: 48px !important;
    padding-inline: 12px !important;
  }

  .ant-card-head-wrapper {
    align-items: flex-start !important;
    flex-wrap: wrap;
    gap: 8px;
    padding-block: 10px;
  }

  .ant-card-extra {
    width: 100%;
    margin-inline-start: 0 !important;
  }

  .ant-card-body {
    padding: 12px !important;
  }

  .ant-table-content,
  .ant-table-body {
    overflow: auto !important;
    overscroll-behavior-inline: contain;
    -webkit-overflow-scrolling: touch;
    touch-action: pan-x pan-y;
  }

  .ant-pagination {
    flex-wrap: wrap;
    gap: 4px 0;
  }

  .ant-modal {
    width: calc(100vw - 24px) !important;
    max-width: calc(100vw - 24px);
    margin: 12px auto;
    top: 12px;
  }

  .ant-tabs-nav-wrap {
    overflow-x: auto !important;
    -webkit-overflow-scrolling: touch;
  }
}
</style>
