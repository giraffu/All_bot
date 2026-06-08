<template>
  <a-card title="实时排队任务监控" :bordered="false" class="shadow-sm hover:shadow-md transition-shadow duration-300 mb-6">
    <template #extra>
      <a-button type="primary" @click="refreshData" :loading="loading">
        <template #icon><ReloadOutlined /></template>
        刷新
      </a-button>
    </template>
    
    <div class="mb-4 text-gray-500 flex justify-between items-center">
      <div>
        当前共有 <strong class="text-blue-500">{{ totalTasks }}</strong> 个任务 正在排队或执行中。
      </div>
      
      <!-- 搜索与筛选区域 -->
      <div class="flex gap-4">
        <a-input-search
          v-model:value="searchText"
          placeholder="搜索用户名称或ID"
          style="width: 250px"
          allow-clear
        />
        <a-select
          v-model:value="statusFilter"
          style="width: 120px"
          placeholder="按状态筛选"
          allow-clear
        >
          <a-select-option value="pending">排队中</a-select-option>
          <a-select-option value="running">生成中</a-select-option>
          <a-select-option value="done">已完成</a-select-option>
          <a-select-option value="error">异常</a-select-option>
          <a-select-option value="cancelled">已取消</a-select-option>
          <a-select-option value="submitting">提交中</a-select-option>
        </a-select>
        <a-select
          v-model:value="typeFilter"
          style="width: 220px"
          placeholder="按任务类型筛选"
          allow-clear
          show-search
          :filter-option="(input, option) => option.label.toLowerCase().includes(input.toLowerCase())"
        >
          <a-select-option
            v-for="option in typeOptions"
            :key="option.value"
            :value="option.value"
            :label="option.label"
          >
            {{ option.label }}
          </a-select-option>
        </a-select>
      </div>
    </div>

    <a-table
      :dataSource="filteredTableData"
      :columns="columns"
      :loading="loading"
      :pagination="{ pageSize: 10, showSizeChanger: true, pageSizeOptions: ['10', '20', '50'] }"
      rowKey="id"
      size="middle"
      :scroll="{ x: 'max-content' }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'user'">
          <div class="flex items-center gap-2">
            <a-avatar :size="24" class="bg-blue-100 text-blue-600">
              <UserOutlined />
            </a-avatar>
            <div class="flex flex-col">
              <span class="font-medium text-gray-800">{{ record.display_name || record.username || 'Unknown' }}</span>
              <span class="text-xs text-gray-500">ID: {{ record.user_id }}</span>
            </div>
          </div>
        </template>
        
        <template v-else-if="column.key === 'identity'">
          <div class="flex flex-col gap-1 items-start">
            <a-tag :color="getGroupColor(record.user_group)" size="small">
              {{ record.user_group || '未知' }}
            </a-tag>
            <a-tag v-if="record.user_identity && record.user_identity !== 'default'" :color="getIdentityColor(record.user_identity)" size="small">
              {{ record.user_identity }}
            </a-tag>
          </div>
        </template>

        <template v-else-if="column.key === 'priority'">
          <a-tag v-if="record.priority !== undefined" color="orange">
            {{ record.priority }}
          </a-tag>
          <span v-else class="text-gray-400">-</span>
        </template>

        <template v-else-if="column.key === 'queue_position'">
          <a-tag v-if="record.queue_position !== undefined && record.queue_position !== '-'" color="purple">
            {{ record.queue_position }}
          </a-tag>
          <span v-else class="text-gray-400">-</span>
        </template>

        <template v-else-if="column.key === 'task_type'">
          <a-tag :color="getTypeColor(record.task_type)">
            {{ record.task_type || 'Unknown' }}
          </a-tag>
        </template>

        <template v-else-if="column.key === 'status'">
          <a-tag v-if="record.execution_status === 'running'" color="processing" class="animate-pulse">
            <template #icon><sync-outlined spin /></template>
            生成中
          </a-tag>
          <a-tag v-else-if="record.execution_status === 'pending'" color="warning">
            排队中
          </a-tag>
          <a-tag v-else-if="record.execution_status === 'done'" color="success">
            已完成
          </a-tag>
          <a-tag v-else-if="record.execution_status === 'error'" color="error">
            异常
          </a-tag>
          <a-tag v-else-if="record.execution_status === 'cancelled'" color="default">
            已取消
          </a-tag>
          <a-tag v-else color="default">
            提交中
          </a-tag>
        </template>

        <template v-else-if="column.key === 'duration'">
          <span v-if="record.created_at" class="text-gray-600 font-mono">
            {{ formatDuration(record.created_at) }}
          </span>
          <span v-else class="text-gray-400">-</span>
        </template>

        <template v-else-if="column.key === 'backend_task_id'">
          <span v-if="record.backend_task_id" class="text-xs font-mono text-gray-500 bg-gray-100 px-2 py-1 rounded">
            {{ record.backend_task_id.substring(0, 8) }}...
          </span>
          <a-tag v-else color="warning">提交中</a-tag>
        </template>
        
        <template v-else-if="column.key === 'action'">
          <a-popconfirm
            title="确定要强制终止并全额退款吗？"
            ok-text="确认终止"
            cancel-text="取消"
            @confirm="handleForceRefund(record.id)"
          >
            <a-button type="link" danger size="small">
              终止退款
            </a-button>
          </a-popconfirm>
        </template>
      </template>
    </a-table>
  </a-card>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ReloadOutlined, UserOutlined, SyncOutlined } from '@ant-design/icons-vue'
import { fetchActiveBotTasks, refundBotTask } from '../api/api'
import { message } from 'ant-design-vue'
import { TASK_TYPE_LABELS, getTaskTypeLabel } from '../constants/taskTypes'

const loading = ref(false)
const tableData = ref([])
const totalTasks = ref(0)
let timer = null

// 搜索与筛选状态
const searchText = ref('')
const statusFilter = ref(undefined)
const typeFilter = ref(undefined)

const typeOptions = computed(() => {
  const knownTypes = Object.keys(TASK_TYPE_LABELS).filter(type => type !== 'unknown')
  const activeTypes = tableData.value
    .map(item => item.task_type)
    .filter(Boolean)
  const mergedTypes = Array.from(new Set([...activeTypes, ...knownTypes]))

  return mergedTypes
    .map(type => ({
      value: type,
      label: getTaskTypeLabel(type) === type ? type : `${getTaskTypeLabel(type)} (${type})`,
    }))
    .sort((a, b) => a.label.localeCompare(b.label, 'zh-CN'))
})

// 计算过滤后的数据
const filteredTableData = computed(() => {
  return tableData.value.filter(item => {
    // 1. 搜索名称或ID
    const searchMatch = !searchText.value || 
      (item.display_name && item.display_name.toLowerCase().includes(searchText.value.toLowerCase())) ||
      (item.username && item.username.toLowerCase().includes(searchText.value.toLowerCase())) ||
      (item.user_id && item.user_id.toString().includes(searchText.value))
      
    // 2. 状态筛选
    const statusMatch = !statusFilter.value || item.execution_status === statusFilter.value
    
    // 3. 任务类型筛选
    const typeMatch = !typeFilter.value || item.task_type === typeFilter.value
    
    return searchMatch && statusMatch && typeMatch
  })
})

const columns = [
  {
    title: '用户',
    key: 'user',
    width: 200,
  },
  {
    title: '修为/身份',
    key: 'identity',
    width: 150,
  },
  {
    title: '优先级',
    key: 'priority',
    dataIndex: 'priority',
    width: 90,
    sorter: (a, b) => (a.priority || 0) - (b.priority || 0),
  },
  {
    title: '排队位置',
    key: 'queue_position',
    dataIndex: 'queue_position',
    width: 100,
    sorter: (a, b) => {
      const getVal = (val) => {
        if (val === '生成中') return -1;
        if (val === '提交中' || val === '-') return 9999;
        return parseInt(val) || 9999;
      };
      return getVal(a.queue_position) - getVal(b.queue_position);
    },
  },
  {
    title: '任务类型',
    key: 'task_type',
    dataIndex: 'task_type',
    width: 120,
  },
  {
    title: '状态',
    key: 'status',
    width: 100,
  },
  {
    title: '已排队时长',
    key: 'duration',
    width: 120,
    sorter: (a, b) => (b.created_at || 0) - (a.created_at || 0),
  },
  {
    title: '后端任务ID',
    key: 'backend_task_id',
    dataIndex: 'backend_task_id',
    width: 150,
  },
  {
    title: '注册ID (Redis)',
    dataIndex: 'id',
    key: 'id',
    width: 250,
    ellipsis: true,
    customRender: ({ text }) => {
      return text ? text.substring(0, 13) + '...' : '-'
    }
  },
  {
    title: '操作',
    key: 'action',
    width: 100,
    fixed: 'right',
  }
]

const getTypeColor = (type) => {
  if (!type) return 'default'
  if (type.includes('video')) return 'purple'
  if (type.includes('face')) return 'cyan'
  if (type.includes('image')) return 'blue'
  return 'geekblue'
}

const currentTime = ref(Math.floor(Date.now() / 1000))
let timeTimer = null

const formatDuration = (createdAt) => {
  if (!createdAt) return '-';
  const diff = currentTime.value - Math.floor(createdAt);
  if (diff < 0) return '0秒';
  
  if (diff < 60) return `${diff}秒`;
  const minutes = Math.floor(diff / 60);
  const seconds = diff % 60;
  if (minutes < 60) {
    return `${minutes}分 ${seconds}秒`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMins = minutes % 60;
  return `${hours}小时 ${remainingMins}分`;
}

const getGroupColor = (group) => {
  const colors = {
    '凡人': 'default',
    '练气期': 'green',
    '筑基期': 'cyan',
    '金丹期': 'gold'
  }
  return colors[group] || 'default'
}

const getIdentityColor = (identity) => {
  const colors = {
    '外门弟子': 'default',
    '内门弟子': 'blue',
    '核心弟子': 'purple',
    '真传弟子': 'magenta'
  }
  return colors[identity] || 'default'
}

const loadData = async () => {
  try {
    const res = await fetchActiveBotTasks()
    if (res.status === 'success') {
      // Transform object to array
      const tasksArray = Object.keys(res.tasks).map(key => ({
        id: key,
        ...res.tasks[key]
      }))
      tableData.value = tasksArray
      totalTasks.value = res.count
    } else {
      console.error('Failed to load active tasks:', res.message)
    }
  } catch (error) {
    console.error('Error fetching active tasks:', error)
  }
}

const refreshData = async () => {
  loading.value = true
  await loadData()
  loading.value = false
  message.success('排队任务已刷新')
}

const handleForceRefund = async (taskId) => {
  try {
    const res = await refundBotTask(taskId)
    if (res.status === 'success') {
      message.success('任务已终止，并已退款')
      await loadData()
    } else {
      message.error('操作失败: ' + res.message)
    }
  } catch (error) {
    console.error('Error refunding task:', error)
    message.error('操作异常')
  }
}

onMounted(() => {
  loadData()
  // Auto refresh every 15 seconds
  timer = setInterval(loadData, 15000)
  // Update time every second for duration display
  timeTimer = setInterval(() => {
    currentTime.value = Math.floor(Date.now() / 1000)
  }, 1000)
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
  }
  if (timeTimer) {
    clearInterval(timeTimer)
  }
})
</script>
