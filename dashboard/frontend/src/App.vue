<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { fetchStats, fetchUsers, fetchUserHistory, fetchStatsHistory } from './api/api'
import StatsCards from './components/StatsCards.vue'
import QueueStats from './components/QueueStats.vue'
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
import LogTable from './components/LogTable.vue'
import { 
  ReloadOutlined, 
  UserOutlined, 
  PictureOutlined, 
  DashboardOutlined,
  SettingOutlined,
  LogoutOutlined,
  MenuUnfoldOutlined,
  MenuFoldOutlined,
  SearchOutlined,
  BellOutlined,
  HomeOutlined,
  PieChartOutlined,
  HistoryOutlined,
  FileTextOutlined
} from '@ant-design/icons-vue'

// State
const activeTab = ref(['home'])
const collapsed = ref(false)
const users = ref([])
const stats = ref({
  total_users: 0,
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
  loadUsers()
}

// Auto refresh when switching tabs
watch(activeTab, (newTab) => {
  const tab = newTab[0]
  if (tab === 'home') {
    loadStats()
    loadHistory()
  } else if (tab === 'users') {
    loadUsers()
  }
  // history and templates components handle their own data fetching on mount
})

onMounted(() => {
  refreshData()
})
</script>

<template>
  <a-layout class="min-h-screen">
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
          <span>首页看板</span>
        </a-menu-item>
        <a-menu-item key="users">
          <template #icon><user-outlined /></template>
          <span>用户管理</span>
        </a-menu-item>
        <a-menu-item key="history">
          <template #icon><history-outlined /></template>
          <span>历史生成</span>
        </a-menu-item>
        <a-menu-item key="logs">
          <template #icon><file-text-outlined /></template>
          <span>操作日志</span>
        </a-menu-item>
        <a-menu-item key="templates">
          <template #icon><picture-outlined /></template>
          <span>模板共建</span>
        </a-menu-item>
        <a-menu-divider />
        <a-menu-item key="settings" disabled>
          <template #icon><setting-outlined /></template>
          <span>系统设置</span>
        </a-menu-item>
      </a-menu>

      <div class="sidebar-footer" v-if="!collapsed">
        <div class="text-xs text-gray-500 mb-2">v1.2.0-stable</div>
        <a-button type="link" danger block class="flex items-center justify-center gap-2 p-0 h-auto">
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
                activeTab[0] === 'home' ? '首页看板' : 
                activeTab[0] === 'users' ? '用户管理' : 
                activeTab[0] === 'history' ? '历史生成' :
                activeTab[0] === 'logs' ? '操作日志' :
                '模板共建' 
              }}
            </a-breadcrumb-item>
          </a-breadcrumb>
        </div>

        <div class="flex items-center gap-6">
          <div class="hidden md:flex items-center bg-gray-100 rounded-full px-4 py-1.5 gap-2 border border-transparent focus-within:border-blue-400 focus-within:bg-white transition-all">
            <search-outlined class="text-gray-400" />
            <input 
              type="text" 
              placeholder="快速搜索..." 
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
                <a-menu-item danger>退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>

      <!-- Content -->
      <a-layout-content 
        class="p-6 bg-gray-50 flex flex-col h-[calc(100vh-64px)]"
        :class="['home', 'templates', 'logs'].includes(activeTab[0]) ? 'overflow-y-auto' : 'overflow-hidden'"
      >
        <div class="w-full flex-1 flex flex-col">
          <!-- Main Workspace -->
          <div v-if="activeTab[0] === 'home'" class="flex-1 flex flex-col gap-6">
            <QueueStats />
            <StatsCards :stats="stats" />
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div class="h-80">
                <DailyTypeChart 
                  title="生成类型分布" 
                  donut
                />
              </div>
              <div class="h-80">
                <HourlyChart 
                  title="分时生成量" 
                />
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div class="h-80">
                <CumulativeTypeChart 
                  title="累计生成类型分布" 
                  donut
                />
              </div>
              <div class="h-80">
                <CumulativeHourlyChart 
                  title="累计分时生成量" 
                />
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div class="h-80">
                <GenerationDistributionChart 
                  title="用户生成量分布" 
                  :data="stats.generation_distribution"
                />
              </div>
              <div class="h-80">
                <AvgDailyDistributionChart 
                  title="用户日均生成量分布" 
                  :data="stats.avg_daily_distribution"
                />
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div class="h-80">
                <CreditDistributionChart 
                  title="用户积分消耗分布" 
                  :data="stats.credit_distribution"
                />
              </div>
              <div class="h-80">
                <AvgDailyCreditDistributionChart 
                  title="用户日均积分消耗分布" 
                  :data="stats.avg_daily_credit_distribution"
                />
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div class="h-80">
                <CreditHoldingDistributionChart 
                  title="用户持有积分分布" 
                  :data="stats.credit_holding_distribution"
                />
              </div>
            </div>

            <div class="flex flex-col gap-6">
              <div class="flex items-center justify-between px-2">
                <h3 class="text-lg font-semibold text-gray-800 m-0">历史趋势 (最近 {{ historyTimeRange }} 天)</h3>
                <a-radio-group 
                  v-model:value="historyTimeRange" 
                  @change="loadHistory"
                  button-style="solid"
                  size="small"
                >
                  <a-radio-button 
                    v-for="opt in timeRangeOptions" 
                    :key="opt.value" 
                    :value="opt.value"
                  >
                    {{ opt.label }}
                  </a-radio-button>
                </a-radio-group>
              </div>

              <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                <div class="h-80">
                  <LineChart 
                    title="用户增长 (每日)" 
                    :data="statsHistory" 
                    :metrics="['new_users', 'new_users_all']"
                  />
                </div>
                <div class="h-80">
                  <LineChart 
                    title="用户每日增长率" 
                    :data="statsHistory" 
                    :metrics="['growth_rate']"
                  />
                </div>
              </div>

              <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                <div class="h-80">
                  <LineChart 
                    title="总用户数量" 
                    :data="cumulativeStatsHistory" 
                    :metrics="['cumulative_users']"
                  />
                </div>
              </div>
              
              <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div class="h-80">
                  <LineChart 
                    title="生成量与灵石消耗" 
                    :data="statsHistory" 
                    :metrics="['generations', 'consumed_credits']"
                  />
                </div>
                <div class="h-80">
                  <LineChart 
                    title="活跃与签到" 
                    :data="statsHistory" 
                    :metrics="['active_users', 'checkins']"
                  />
                </div>
              </div>
            </div>
          </div>

          <div v-else-if="activeTab[0] === 'users'" class="flex-1 bg-white rounded-xl shadow-sm border p-6 flex flex-col min-h-0">
            <UserTable 
              :users="users" 
              :loading="loading" 
              :error="error" 
              @view-history="viewHistory" 
              @refresh="refreshData"
            />
          </div>

          <div v-else-if="activeTab[0] === 'history'" class="flex-1 bg-white rounded-xl shadow-sm border p-6 flex flex-col min-h-0">
            <HistoryTable />
          </div>

          <div v-else-if="activeTab[0] === 'logs'" class="flex-1 bg-white rounded-xl shadow-sm border p-6 flex flex-col min-h-0">
            <LogTable />
          </div>

          <div v-else-if="activeTab[0] === 'templates'" class="flex-1 bg-white rounded-xl shadow-sm border p-6 flex flex-col min-h-0">
            <TemplateManager />
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
