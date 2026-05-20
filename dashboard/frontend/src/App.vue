<script setup>
import { ref, onMounted, watch, onUnmounted } from 'vue'
import Login from './components/Login.vue'
import HistoryModal from './components/HistoryModal.vue'
import {
  UserOutlined,
  MenuUnfoldOutlined,
  MenuFoldOutlined,
  ReloadOutlined,
  BellOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'
import { useDashboardOverview } from './composables/useDashboardOverview'
import { useDashboardTaskSearch } from './composables/useDashboardTaskSearch'
import { useDashboardUserHistory } from './composables/useDashboardUserHistory'
import { useDashboardNavigation } from './composables/useDashboardNavigation'
import { useDashboardTabView } from './composables/useDashboardTabView'

const isAuthenticated = ref(!!localStorage.getItem('token'))
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

const handleLoginSuccess = () => {
  isAuthenticated.value = true
  void refreshData()
}

const handleLogout = () => {
  localStorage.removeItem('token')
  isAuthenticated.value = false
}

const handleUnauthorized = () => {
  isAuthenticated.value = false
}

onMounted(() => {
  window.addEventListener('unauthorized', handleUnauthorized)
  if (isAuthenticated.value) {
    void refreshData()
  }
})

onUnmounted(() => {
  window.removeEventListener('unauthorized', handleUnauthorized)
})
</script>

<template>
  <Login v-if="!isAuthenticated" @login-success="handleLoginSuccess" />
  
  <a-layout v-else class="min-h-screen">
    <!-- Sidebar -->
    <a-layout-sider 
      v-model:collapsed="collapsed" 
      :trigger="null" 
      collapsible
      theme="dark"
      class="sidebar-shadow z-50"
      width="240"
    >
      <div class="logo-container">
        <div class="logo-icon">T</div>
        <span v-if="!collapsed" class="logo-text">TeleBot Admin</span>
      </div>
      
      <a-menu v-model:selectedKeys="activeTab" theme="dark" mode="inline">
        <a-menu-item
          v-for="item in menuItems"
          :key="item.key"
          :disabled="item.disabled"
        >
          <template #icon>
            <component :is="item.icon" />
          </template>
          <span>{{ item.label }}</span>
        </a-menu-item>
      </a-menu>

      <div class="sidebar-footer" v-if="!collapsed">
        <div class="text-xs text-gray-500 mb-2">v1.2.0-stable</div>
        <a-button @click="handleLogout" type="link" danger block class="flex items-center justify-center gap-2 p-0 h-auto">
          <component :is="logoutIcon" /> 退出登录
        </a-button>
      </div>
    </a-layout-sider>

    <a-layout>
      <!-- Header -->
      <a-layout-header class="bg-white border-b px-6 flex justify-between items-center h-16 shrink-0 z-40">
        <div class="flex items-center gap-4">
          <component 
            :is="collapsed ? MenuUnfoldOutlined : MenuFoldOutlined"
            class="trigger text-lg cursor-pointer hover:text-blue-600 transition-colors"
            @click="collapsed = !collapsed"
          />
          <a-breadcrumb class="hidden sm:block">
            <a-breadcrumb-item>首页</a-breadcrumb-item>
            <a-breadcrumb-item>{{ currentTabTitle }}</a-breadcrumb-item>
          </a-breadcrumb>
        </div>

        <div class="flex items-center gap-6">
          <div class="hidden md:flex items-center bg-gray-100 rounded-full px-4 py-1.5 gap-2 border border-transparent focus-within:border-blue-400 focus-within:bg-white transition-all">
            <search-outlined class="text-gray-400" />
            <input 
              v-model="searchQuery"
              @keyup.enter="handleSearch"
              type="text" 
              placeholder="输入任务ID回车搜索..." 
              class="bg-transparent border-none outline-none text-sm w-48 text-gray-600 placeholder-gray-400"
            />
          </div>
          
          <div class="flex items-center gap-3">
            <a-badge dot color="green">
              <a-button shape="circle" size="small" class="flex items-center justify-center border-none shadow-none">
                <template #icon><bell-outlined /></template>
              </a-button>
            </a-badge>
            
            <a-tooltip title="刷新数据">
              <a-button 
                shape="circle"
                size="small"
                @click="refreshData" 
                :loading="refreshLoading"
                class="flex items-center justify-center border-none shadow-none"
              >
                <template #icon><reload-outlined /></template>
              </a-button>
            </a-tooltip>
          </div>
          <div class="h-8 w-px bg-gray-200"></div>
          <a-dropdown placement="bottomRight">
            <div class="flex items-center gap-2 cursor-pointer group">
              <a-avatar style="background-color: #1890ff">
                <template #icon><user-outlined /></template>
              </a-avatar>
              <span class="text-gray-600 group-hover:text-blue-600 transition-colors">管理员</span>
            </div>
            <template #overlay>
              <a-menu>
                <a-menu-item>个人中心</a-menu-item>
                <a-menu-item danger @click="handleLogout">退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>

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

    <!-- Task Search Result Modal -->
    <a-modal
      v-model:visible="searchModalVisible"
      title="任务状态查询"
      @cancel="closeSearchModal"
      :footer="null"
      width="600px"
    >
      <div v-if="searchResult" class="flex flex-col gap-4">
        <div class="flex justify-between items-center p-3 bg-gray-50 rounded">
          <span class="font-bold text-gray-600">任务ID:</span>
          <span class="font-mono text-xs select-all">{{ searchResult.id }}</span>
        </div>
        
        <div class="flex justify-between items-center p-3 bg-gray-50 rounded">
          <span class="font-bold text-gray-600">状态:</span>
          <a-tag :color="getStatusColor(searchResult.status)" class="text-lg px-3 py-1">
            {{ searchResult.status ? searchResult.status.toUpperCase() : 'UNKNOWN' }}
          </a-tag>
        </div>

        <div v-if="searchResult.status === 'pending'" class="flex flex-col gap-2 p-3 bg-orange-50 rounded border border-orange-100">
          <div class="flex justify-between">
            <span class="text-orange-800">当前队列位置:</span>
            <span class="font-bold text-orange-600">{{ searchResult.queue_pos }}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-orange-800">剩余等待数:</span>
            <span class="font-bold text-orange-600">{{ searchResult.queue_remaining }}</span>
          </div>
        </div>

        <div v-if="searchResult.status === 'running'" class="flex flex-col gap-2 p-3 bg-blue-50 rounded border border-blue-100">
          <div class="flex justify-between mb-1">
             <span class="text-blue-800">生成进度:</span>
             <span class="font-bold text-blue-600">{{ Math.round((searchResult.progress || 0) * 100) }}%</span>
          </div>
          <a-progress :percent="Math.round((searchResult.progress || 0) * 100)" status="active" />
        </div>

        <div v-if="searchResult.status === 'done'" class="flex flex-col gap-2">
          <div v-if="isImage(searchResult.result_path)" class="rounded-lg overflow-hidden border shadow-sm">
            <img :src="getTaskImageUrl(searchResult.id)" class="w-full object-contain max-h-[500px] bg-gray-100" />
          </div>
          <div v-else-if="isVideo(searchResult.result_path)" class="rounded-lg overflow-hidden border shadow-sm">
            <video controls :src="getTaskVideoUrl(searchResult.id)" class="w-full max-h-[500px] bg-black"></video>
          </div>
          <div v-else class="p-4 bg-green-50 text-green-700 rounded border border-green-200">
             任务已完成，结果文件: {{ searchResult.result_path }}
          </div>
          <a-button type="primary" block :href="isImage(searchResult.result_path) ? getTaskImageUrl(searchResult.id) : getTaskVideoUrl(searchResult.id)" target="_blank" class="mt-2">
            下载/查看原文件
          </a-button>
        </div>
        
        <div v-if="searchResult.status === 'error'" class="p-4 bg-red-50 text-red-700 rounded border border-red-200">
          <div class="font-bold mb-1">错误信息:</div>
          <div class="font-mono text-sm whitespace-pre-wrap">{{ searchResult.error }}</div>
        </div>
      </div>
    </a-modal>
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
