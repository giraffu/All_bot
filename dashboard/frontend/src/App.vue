<script setup>
import { ref, watch } from 'vue'
import Login from './components/Login.vue'
import HistoryModal from './components/HistoryModal.vue'
import DashboardSidebar from './components/DashboardSidebar.vue'
import DashboardHeaderBar from './components/DashboardHeaderBar.vue'
import DashboardTaskSearchModal from './components/DashboardTaskSearchModal.vue'
import { useDashboardAuth } from './composables/useDashboardAuth'
import { useDashboardOverview } from './composables/useDashboardOverview'
import { useDashboardTaskSearch } from './composables/useDashboardTaskSearch'
import { useDashboardUserHistory } from './composables/useDashboardUserHistory'
import { useDashboardNavigation } from './composables/useDashboardNavigation'
import { useDashboardTabView } from './composables/useDashboardTabView'

const { isAuthenticated, clearAuthToken } = useDashboardAuth()
const activeTab = ref(['home'])
const collapsed = ref(false)
const {
  stats,
  statsHistory,
  cumulativeStatsHistory,
  historyTimeRange,
  refreshLoading,
  timeRangeOptions,
  loadHistory,
  refreshData
} = useDashboardOverview()
const {
  searchQuery,
  searchResult,
  searchModalVisible,
  searchLoading,
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
  viewHistory,
  closeModal
} = useDashboardUserHistory()
const { menuItems, scrollableTabKeys, currentTabTitle, logoutIcon } =
  useDashboardNavigation(activeTab)
const { currentTabView } = useDashboardTabView(
  activeTab,
  {
    stats,
    statsHistory,
    cumulativeStatsHistory,
    historyTimeRange,
    timeRangeOptions,
    loadHistory,
  },
  {
    viewHistory,
  }
)

// Auto refresh when switching tabs
watch(activeTab, (newTab) => {
  const tab = newTab[0]
  if (tab === 'home' || tab === 'finance') {
    void refreshData()
  }
  // UserTable, history, templates handle their own data fetching
})

watch(
  isAuthenticated,
  (authenticated) => {
    if (authenticated) {
      void refreshData()
    }
  },
  { immediate: true }
)

const handleLogout = () => {
  clearAuthToken()
}
</script>

<template>
  <Login v-if="!isAuthenticated" />
  
  <a-layout v-else class="min-h-screen">
    <dashboard-sidebar
      v-model:collapsed="collapsed"
      v-model:active-tab="activeTab"
      :menu-items="menuItems"
      :logout-icon="logoutIcon"
      @logout="handleLogout"
    />

    <a-layout>
      <dashboard-header-bar
        v-model:collapsed="collapsed"
        v-model:search-query="searchQuery"
        :current-tab-title="currentTabTitle"
        :refresh-loading="refreshLoading"
        @search="handleSearch"
        @refresh="refreshData"
        @logout="handleLogout"
      />

      <!-- Content -->
      <a-layout-content 
        class="p-6 bg-gray-50 flex flex-col h-[calc(100vh-64px)]"
        :class="scrollableTabKeys.includes(activeTab[0]) ? 'overflow-y-auto' : 'overflow-hidden'"
      >
        <div class="w-full flex-1 flex flex-col">
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
      @close="closeModal" 
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
/* Global styles */
@import 'tailwindcss/base';
@import 'tailwindcss/components';
@import 'tailwindcss/utilities';

html, body, #app {
  height: 100%;
  width: 100%;
  margin: 0;
  padding: 0;
  overflow: hidden;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
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
</style>
