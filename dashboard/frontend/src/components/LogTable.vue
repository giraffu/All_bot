<script setup>
import { ref, onMounted, reactive, watch } from 'vue'
import { fetchLogs } from '../api/api'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import dayjs from 'dayjs'

const logs = ref([])
const loading = ref(false)
const total = ref(0)
const pagination = reactive({
  current: 1,
  pageSize: 20,
  showSizeChanger: true,
  pageSizeOptions: ['10', '20', '50', '100']
})

const filters = reactive({
  userId: '',
  username: '',
  operationType: undefined,
  dateRange: []
})

const columns = [
  {
    title: 'ID',
    dataIndex: 'id',
    width: 80,
  },
  {
    title: '用户',
    dataIndex: 'user_info',
    width: 200,
  },
  {
    title: '操作类型',
    dataIndex: 'operation_type',
    width: 150,
  },
  {
    title: '积分变动',
    dataIndex: 'credit_change',
    width: 120,
    align: 'right'
  },
  {
    title: '当前余额',
    dataIndex: 'current_balance',
    width: 120,
    align: 'right'
  },
  {
    title: '时间',
    dataIndex: 'created_at',
    width: 180,
  },
  {
    title: '附加信息',
    dataIndex: 'extra_info',
    ellipsis: true
  }
]

const operationTypes = [
  { label: '签到 (Checkin)', value: 'checkin' },
  { label: '生成消耗 (Generation)', value: 'generation' },
  { label: '充值成功 (Recharge)', value: 'recharge' },
  { label: '邀请奖励 (Referral)', value: 'referral_reward_initial' },
  { label: '新人奖励 (Welcome)', value: 'welcome_bonus' },
  { label: '入群奖励 (Channel)', value: 'referral_reward_channel' },
  { label: '生成邀请奖励 (Generation Referral)', value: 'referral_reward_generation' },
  { label: '模板贡献 (Template)', value: 'template_submission' }
]

const loadLogs = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.current,
      pageSize: pagination.pageSize,
      userId: filters.userId || null,
      username: filters.username || null,
      operationType: filters.operationType || null,
      startDate: filters.dateRange?.[0] ? dayjs(filters.dateRange[0]).format('YYYY-MM-DD') : null,
      endDate: filters.dateRange?.[1] ? dayjs(filters.dateRange[1]).format('YYYY-MM-DD') : null
    }
    
    const res = await fetchLogs(params)
    logs.value = res.items
    total.value = res.total
  } catch (err) {
    console.error('Failed to load logs:', err)
  } finally {
    loading.value = false
  }
}

const handleTableChange = (pag) => {
  pagination.current = pag.current
  pagination.pageSize = pag.pageSize
  loadLogs()
}

const onSearch = () => {
  pagination.current = 1
  loadLogs()
}

const resetFilters = () => {
  filters.userId = ''
  filters.username = ''
  filters.operationType = undefined
  filters.dateRange = []
  onSearch()
}

const formatDate = (dateStr) => {
  return dayjs(dateStr).format('YYYY-MM-DD HH:mm:ss')
}

const formatExtraInfo = (info) => {
  if (!info) return '-'
  try {
    // If it's already an object, just JSON stringify it for display
    // Or format specific fields if needed
    return JSON.stringify(info)
  } catch (e) {
    return String(info)
  }
}

onMounted(() => {
  loadLogs()
})
</script>

<template>
  <div class="flex flex-col h-full gap-4">
    <!-- Header / Filters -->
    <div class="flex flex-wrap items-center justify-between gap-4 bg-gray-50 p-4 rounded-lg border">
      <div class="flex flex-wrap items-center gap-3">
        <a-input 
          v-model:value="filters.userId" 
          placeholder="用户 ID" 
          style="width: 150px" 
          allow-clear
          @pressEnter="onSearch"
        >
          <template #prefix><search-outlined class="text-gray-400" /></template>
        </a-input>

        <a-input 
          v-model:value="filters.username" 
          placeholder="用户名" 
          style="width: 160px" 
          allow-clear
          @pressEnter="onSearch"
        >
          <template #prefix><search-outlined class="text-gray-400" /></template>
        </a-input>

        <a-select
          v-model:value="filters.operationType"
          placeholder="操作类型"
          style="width: 180px"
          allow-clear
          @change="onSearch"
        >
          <a-select-option v-for="opt in operationTypes" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </a-select-option>
        </a-select>

        <a-range-picker 
          v-model:value="filters.dateRange" 
          @change="onSearch"
          style="width: 240px"
        />

        <a-button type="primary" @click="onSearch">查询</a-button>
        <a-button @click="resetFilters">重置</a-button>
      </div>
      
      <a-button @click="loadLogs" :loading="loading">
        <template #icon><reload-outlined /></template>
        刷新
      </a-button>
    </div>

    <!-- Table -->
    <div class="flex-1 overflow-hidden bg-white rounded-lg border shadow-sm">
      <a-table
        :columns="columns"
        :data-source="logs"
        :pagination="{ ...pagination, total }"
        :loading="loading"
        @change="handleTableChange"
        row-key="id"
        size="middle"
        :scroll="{ y: 'calc(100vh - 280px)' }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'user_info'">
            <div class="flex flex-col">
              <span class="font-medium text-gray-800">{{ record.username || '未知用户' }}</span>
              <span class="text-xs text-gray-500">ID: {{ record.user_id }}</span>
            </div>
          </template>

          <template v-else-if="column.dataIndex === 'operation_type'">
            <a-tag :color="record.operation_type === 'checkin' ? 'green' : 
                          record.operation_type === 'generation' ? 'blue' : 
                          record.operation_type === 'recharge' ? 'purple' :
                          record.operation_type.includes('reward') ? 'gold' : 'default'">
              {{ record.operation_type }}
            </a-tag>
          </template>

          <template v-else-if="column.dataIndex === 'credit_change'">
            <span :class="record.credit_change > 0 ? 'text-green-600 font-medium' : 'text-red-500 font-medium'">
              {{ record.credit_change > 0 ? '+' : '' }}{{ record.credit_change }}
            </span>
          </template>

          <template v-else-if="column.dataIndex === 'created_at'">
            {{ formatDate(record.created_at) }}
          </template>

          <template v-else-if="column.dataIndex === 'extra_info'">
            <span class="text-gray-500 text-xs font-mono" :title="formatExtraInfo(record.extra_info)">
              {{ formatExtraInfo(record.extra_info) }}
            </span>
          </template>
        </template>
      </a-table>
    </div>
  </div>
</template>
