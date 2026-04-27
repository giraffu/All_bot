<script setup>
import { ref, onMounted, computed, watch, onUnmounted } from 'vue'
import { fetchStats, fetchUsers, fetchUserHistory, fetchStatsHistory, fetchTaskStatus, fetchTaskImage, fetchTaskVideo } from './api/api'
import HomeDashboard from "./components/HomeDashboard.vue"
import FinanceDashboard from "./components/FinanceDashboard.vue"
import Login from './components/Login.vue'
import StatsCards from './components/StatsCards.vue'
import QueueStats from './components/QueueStats.vue'
import ActiveTasksTable from './components/ActiveTasksTable.vue'
import UserTable from './components/UserTable.vue'
import TemplateManager from './components/TemplateManager.vue'
import HistoryModal from './components/HistoryModal.vue'
import PieChart from './components/PieChart.vue'
import LineChart from './components/LineChart.vue'
import HourlyChart from './components/HourlyChart.vue'
import CumulativeHourlyChart from './components/CumulativeHourlyChart.vue'
import GenerationDistributionChart from './components/GenerationDistributionChart.vue'
import AvgDailyDistributionChart from './components/AvgDailyDistributionChart.vue'
import CreditDistributionChart from './components/CreditDistributionChart.vue'
import AvgDailyCreditDistributionChart from './components/AvgDailyCreditDistributionChart.vue'
import CreditHoldingDistributionChart from './components/CreditHoldingDistributionChart.vue'
import DailyTypeChart from './components/DailyTypeChart.vue'
import CumulativeTypeChart from './components/CumulativeTypeChart.vue'
import HistoryTable from './components/HistoryTable.vue'
import WorkerHistoryTable from './components/WorkerHistoryTable.vue'
import LogTable from './components/LogTable.vue'
import RechargeSystem from './components/RechargeSystem.vue'
import GalleryTable from './components/GalleryTable.vue'
import ReferralTable from './components/ReferralTable.vue'
import { message } from 'ant-design-vue'
import {
  UserOutlined,
  HistoryOutlined,
  MenuUnfoldOutlined,
  MenuFoldOutlined,
  HomeOutlined,
  FileTextOutlined,
  PayCircleOutlined,
  PictureOutlined,
  SettingOutlined,
  LogoutOutlined,
  ReloadOutlined,
  DashboardOutlined,
  SearchOutlined,
  BellOutlined,
  PieChartOutlined,
  RobotOutlined,
  AppstoreOutlined,
  BankOutlined,
  GiftOutlined
} from '@ant-design/icons-vue'

// State
const isAuthenticated = ref(!!localStorage.getItem('token'))
const activeTab = ref(['home'])
const collapsed = ref(false)
const users = ref([])
const stats = ref({
  total_users: 0,
  inner_disciple_count: 0,
  core_disciple_count: 0,
  true_disciple_count: 0,
  total_generations: 0,
  total_credits: 0,
  total_active_credits: 0,
  total_referrals: 0,
  total_template_contributions: 0,
  total_approved_contributions: 0,
  today_users: 0,
  today_generations: 0,
  today_active_users: 0,
  today_checkins: 0,
  today_type_distribution: {},
  total_type_distribution: {},
  generation_distribution: {},
  avg_daily_distribution: {},
  credit_distribution: {},
  avg_daily_credit_distribution: {},
  credit_holding_distribution: {}
})
const statsHistory = ref([])
const cumulativeStatsHistory = ref([])
const loading = ref(false)
const error = ref(null)
const historyTimeRange = ref(7) // Default 7 days
const searchQuery = ref('')
const searchResult = ref(null)
const searchModalVisible = ref(false)
const searchLoading = ref(false)

const timeRangeOptions = [
  { label: '最近 7 天', value: 7 },
  { label: '最近 2 周', value: 14 },
  { label: '最近 1 个月', value: 30 },
  { label: '最近 2 个月', value: 60 },
  { label: '最近 3 个月', value: 90 },
  { label: '最近半年', value: 180 },
  { label: '最近 1 年', value: 365 }
]

// Type Mapping
const typeMapping = {
  'undress': '快速脱衣',
  'video_undress': '视频脱衣',
  'face_swap': '快速换脸',
  'faceswap_step1': '快速换脸',
  'faceswap_step2': '快速换脸',
  'random_faceswap': '随机换脸',
  'face_show': '动图露奶',
  'face_tongue': '动图吐舌',
  'fuck': '动图做爱',
  'penetration': '快速抽插',
  'penetration_step1': '快速抽插',
  'penetration_step2': '快速抽插',
  'perfect_video_insert': '动图传教士',
  'doggy_style': '动图后入',
  'blowjob': '脱衣口交',
  'masturbation': '快速自慰',
  'image': '自由P图',
  'edit': '自由P图',
  'video': '视频生成',
  'video_pro': '专业视频',
  'custom_video': '自定义视频',
  'template_contribute': '模板共建',
  'undress_tongue': '脱衣吐舌',
  'closeup_blowjob': '特写口交',
  'text_to_image': '文生图',
  'i2i_pro': '幻想换脸',
  'video_lora': '图生视频(附加模型)',
  'ltx_video': '高级图生视频',
  'unknown': '未知类型'
};

const transformDistribution = (dist) => {
  if (!dist) return [];
  return Object.entries(dist).map(([key, value]) => ({
    name: typeMapping[key] || key,
    value: value
  }));
};

const todayTypeData = computed(() => transformDistribution(stats.value.today_type_distribution));
const totalTypeData = computed(() => transformDistribution(stats.value.total_type_distribution));

// Modal state
const showModal = ref(false)
const selectedUser = ref(null)
const userHistory = ref([])
const historyLoading = ref(false)

const handleSearch = async () => {
  if (!searchQuery.value.trim()) return
  
  searchLoading.value = true
  try {
    const data = await fetchTaskStatus(searchQuery.value.trim())
    if (data) {
      searchResult.value = { ...data, id: searchQuery.value.trim() }
      searchModalVisible.value = true
    }
  } catch (err) {
    console.error('Search error:', err)
    message.error('未找到任务或查询失败')
  } finally {
    searchLoading.value = false
  }
}

const closeSearchModal = () => {
  searchModalVisible.value = false
  searchResult.value = null
}

const isImage = (filename) => /\.(png|jpg|jpeg|webp)$/i.test(filename || '')
const isVideo = (filename) => /\.(mp4|mov|webm)$/i.test(filename || '')
const getTaskImageUrl = (id) => fetchTaskImage(id)
const getTaskVideoUrl = (id) => fetchTaskVideo(id)
const getStatusColor = (status) => {
  switch(status) {
    case 'pending': return 'orange'
    case 'running': return 'blue'
    case 'done': return 'success'
    case 'error': return 'error'
    default: return 'default'
  }
}

// Actions
const loadStats = async () => {
  try {
    stats.value = await fetchStats()
  } catch (err) {
    console.error('Error fetching stats:', err)
  }
}

const loadHistory = async () => {
  try {
    const data = await fetchStatsHistory(historyTimeRange.value)
    statsHistory.value = data
  } catch (err) {
    console.error('Error fetching history:', err)
  }
}

// Watch stats and statsHistory to calculate cumulative
watch([() => stats.value.total_users, statsHistory], ([totalUsers, history]) => {
  if (totalUsers > 0 && history.length > 0) {
    let currentTotal = totalUsers
    const reversedData = [...history].reverse()
    
    const cumulativeData = reversedData.map((day) => {
      const totalForDay = currentTotal
      currentTotal -= day.new_users
      return {
        date: day.date,
        cumulative_users: totalForDay
      }
    }).reverse()
    
    cumulativeStatsHistory.value = cumulativeData
  }
}, { immediate: true })

const loadUsers = async () => {
  loading.value = true
  error.value = null
  try {
    users.value = await fetchUsers()
  } catch (err) {
    console.error('Error fetching users:', err)
    error.value = '无法加载用户列表，请检查后端服务是否启动。'
  } finally {
    loading.value = false
  }
}

const viewHistory = async (user) => {
  selectedUser.value = user
  showModal.value = true
  historyLoading.value = true
  userHistory.value = []
  
  try {
    userHistory.value = await fetchUserHistory(user.id)
  } catch (err) {
    console.error('Error fetching history:', err)
  } finally {
    historyLoading.value = false
  }
}

const closeModal = () => {
  showModal.value = false
  selectedUser.value = null
  userHistory.value = []
}

const refreshData = () => {
  loadStats()
  loadHistory()
  // loadUsers is now handled by UserTable
}

// Auto refresh when switching tabs
watch(activeTab, (newTab) => {
  const tab = newTab[0]
  if (tab === 'home' || tab === 'finance') {
    loadStats()
    loadHistory()
  }
  // UserTable, history, templates handle their own data fetching
})

const handleLoginSuccess = () => {
  isAuthenticated.value = true
  refreshData()
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
    refreshData()
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
          <a-menu-item key="home">
            <template #icon><home-outlined /></template>
            <span>数据大盘</span>
          </a-menu-item>
          <a-menu-item key="finance">
            <template #icon><bank-outlined /></template>
            <span>充值数据</span>
          </a-menu-item>
          <a-menu-item key="monitor">
            <template #icon><dashboard-outlined /></template>
            <span>系统监控</span>
          </a-menu-item>
          <a-menu-item key="users">
            <template #icon><user-outlined /></template>
            <span>用户管理</span>
          </a-menu-item>
        <a-menu-item key="history">
          <template #icon><history-outlined /></template>
          <span>历史生成</span>
        </a-menu-item>
        <a-menu-item key="worker_history">
          <template #icon><robot-outlined /></template>
          <span>Worker记录</span>
        </a-menu-item>
        <a-menu-item key="logs">
          <template #icon><file-text-outlined /></template>
          <span>操作日志</span>
        </a-menu-item>
        <a-menu-item key="recharge">
          <template #icon><pay-circle-outlined /></template>
          <span>充值系统</span>
        </a-menu-item>
        <a-menu-item key="templates">
          <template #icon><picture-outlined /></template>
          <span>模板共建</span>
        </a-menu-item>
        <a-menu-item key="gallery">
          <template #icon><appstore-outlined /></template>
          <span>广场内容管理</span>
        </a-menu-item>
        <a-menu-item key="referrals">
          <template #icon><gift-outlined /></template>
          <span>邀请奖励</span>
        </a-menu-item>
        <a-menu-divider />
        <a-menu-item key="settings" disabled>
          <template #icon><setting-outlined /></template>
          <span>系统设置</span>
        </a-menu-item>
      </a-menu>

      <div class="sidebar-footer" v-if="!collapsed">
        <div class="text-xs text-gray-500 mb-2">v1.2.0-stable</div>
        <a-button @click="handleLogout" type="link" danger block class="flex items-center justify-center gap-2 p-0 h-auto">
          <logout-outlined /> 退出登录
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
            <a-breadcrumb-item>
              {{ 
                activeTab[0] === 'home' ? '数据大盘' : 
                activeTab[0] === 'finance' ? '充值数据' : 
                activeTab[0] === 'users' ? '用户管理' : 
                activeTab[0] === 'history' ? '历史生成' :
                activeTab[0] === 'logs' ? '操作日志' :
                activeTab[0] === 'recharge' ? '充值系统' :
                activeTab[0] === 'gallery' ? '广场内容管理' :
                activeTab[0] === 'referrals' ? '邀请奖励' :
                '模板共建' 
              }}
            </a-breadcrumb-item>
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
                :loading="loading"
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
        :class="['home', 'finance', 'monitor', 'templates', 'logs', 'recharge', 'referrals'].includes(activeTab[0]) ? 'overflow-y-auto' : 'overflow-hidden'"
      >
        <div class="w-full flex-1 flex flex-col">
          <!-- System Monitor Tab -->
          <div v-if="activeTab[0] === 'monitor'" class="flex-1 flex flex-col gap-6">
            <QueueStats />
            <ActiveTasksTable />
          </div>

          <HomeDashboard 
            v-else-if="activeTab[0] === 'home'" 
            :stats="stats" 
            :statsHistory="statsHistory" 
            :cumulativeStatsHistory="cumulativeStatsHistory" 
            v-model:historyTimeRange="historyTimeRange" 
            :timeRangeOptions="timeRangeOptions" 
            @loadHistory="loadHistory" 
          />

          <FinanceDashboard 
            v-else-if="activeTab[0] === 'finance'" 
            :stats="stats" 
            :statsHistory="statsHistory" 
            v-model:historyTimeRange="historyTimeRange" 
            :timeRangeOptions="timeRangeOptions" 
            @loadHistory="loadHistory" 
          />

          <div v-else-if="activeTab[0] === 'users'" class="flex-1 bg-white rounded-xl shadow-sm border p-6 flex flex-col min-h-0">
            <UserTable 
              @view-history="viewHistory" 
            />
          </div>

          <div v-else-if="activeTab[0] === 'history'" class="flex-1 bg-white rounded-xl shadow-sm border p-6 flex flex-col min-h-0">
            <HistoryTable />
          </div>

          <div v-else-if="activeTab[0] === 'worker_history'" class="flex-1 bg-white rounded-xl shadow-sm border p-6 flex flex-col min-h-0">
            <WorkerHistoryTable />
          </div>

          <div v-else-if="activeTab[0] === 'logs'" class="flex-1 bg-white rounded-xl shadow-sm border p-6 flex flex-col min-h-0">
            <LogTable />
          </div>

          <div v-else-if="activeTab[0] === 'recharge'" class="flex-1 min-h-0">
            <RechargeSystem />
          </div>

          <div v-else-if="activeTab[0] === 'templates'" class="flex-1 bg-white rounded-xl shadow-sm border p-6 flex flex-col min-h-0">
            <TemplateManager />
          </div>

          <div v-else-if="activeTab[0] === 'gallery'" class="flex-1 bg-white rounded-xl shadow-sm border p-6 flex flex-col min-h-0">
            <GalleryTable />
          </div>

          <div v-else-if="activeTab[0] === 'referrals'" class="flex-1 flex flex-col min-h-0">
            <ReferralTable />
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
