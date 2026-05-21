<script setup>
import { ref, onMounted } from 'vue'
import { fetchHistoryAll, fetchWorkerList } from '../api/api'
import { getFileUrl, formatDate } from '../utils/helpers'
import { getTaskTypeLabel, TASK_TYPE_OPTIONS } from '../constants/taskTypes'
import MediaItem from './MediaItem.vue'
import { 
  UserOutlined,
  ReloadOutlined,
  SearchOutlined,
  CloseCircleFilled
} from '@ant-design/icons-vue'

const loading = ref(false)
const history = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const selectedTypes = ref([])
const selectedRating = ref(null)
const selectedPublic = ref(null)
const selectedWorker = ref(null)
const workerOptions = ref([{ label: '全部节点', value: null }])

const typeOptions = TASK_TYPE_OPTIONS

const ratingOptions = [
  { label: '全部评价', value: null },
  { label: '👍 已点赞', value: 1 },
  { label: '👎 已点踩', value: -1 },
  { label: '⏳ 未评价', value: 0 }
];

const publicOptions = [
  { label: '全部状态', value: null },
  { label: '🌐 已公开', value: true },
  { label: '🔒 私有', value: false }
];

// Data fetching
const loadData = async (page = 1) => {
  loading.value = true
  try {
    const typeParam = selectedTypes.value.length > 0 ? selectedTypes.value.join(',') : null
    const data = await fetchHistoryAll(page, pageSize.value, typeParam, selectedRating.value, selectedPublic.value, selectedWorker.value)
    history.value = data.items
    total.value = data.total
    currentPage.value = page
  } catch (err) {
    console.error('Failed to load history:', err)
  } finally {
    loading.value = false
  }
}

const loadWorkers = async () => {
  try {
    const data = await fetchWorkerList()
    if (data && data.workers && data.workers.length > 0) {
      const options = data.workers.map(w => ({ label: w, value: w }))
      workerOptions.value = [{ label: '全部节点', value: null }, ...options]
    }
  } catch (err) {
    console.error('Failed to load workers:', err)
  }
}

const handleFilterChange = () => {
  loadData(1)
}

const resetFilters = () => {
  selectedTypes.value = []
  selectedRating.value = null
  selectedPublic.value = null
  selectedWorker.value = null
  loadData(1)
}

// Columns
const columns = [
  {
    title: '生成时间',
    dataIndex: 'created_at',
    key: 'created_at',
    width: 150,
  },
  {
    title: '用户',
    dataIndex: 'user_id',
    key: 'user',
    width: 200,
  },
  {
    title: '类型',
    dataIndex: 'type',
    key: 'type',
    width: 120,
  },
  {
    title: '来源',
    dataIndex: 'source',
    key: 'source',
    width: 80,
  },
  {
    title: '生成节点',
    dataIndex: 'worker_id',
    key: 'worker_id',
    width: 120,
  },
  {
    title: '输入内容',
    dataIndex: 'input_file',
    key: 'input',
    width: 250,
  },
  {
    title: '输出内容',
    dataIndex: 'output_file',
    key: 'output',
    width: 150,
  },
  {
    title: 'Prompt',
    dataIndex: 'prompt',
    key: 'prompt',
  },
]

const handleTableChange = (pagination) => {
  loadData(pagination.current)
}

const refreshData = () => {
  loadData(currentPage.value)
}

onMounted(() => {
  loadData()
  loadWorkers()
})
</script>

<template>
  <div class="h-full flex flex-col bg-white rounded-xl shadow-sm border p-6">
    <div class="mb-4 flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-4">
          <h2 class="text-xl font-bold text-gray-800 m-0">历史生成记录</h2>
          
          <!-- Filters Group -->
          <div class="flex items-center gap-3 bg-gray-50 px-3 py-2 rounded-xl border border-gray-100 shadow-sm">
            <!-- Multiple Type Filter -->
            <div class="flex items-center gap-2">
              <span class="text-gray-500 text-xs font-medium">类型:</span>
              <a-select
                v-model:value="selectedTypes"
                mode="multiple"
                style="min-width: 180px; max-width: 300px"
                placeholder="全部类型"
                @change="handleFilterChange"
                :options="typeOptions"
                size="small"
                show-search
                allow-clear
                option-filter-prop="label"
                max-tag-count="responsive"
                class="custom-select"
              />
            </div>

            <div class="h-4 w-[1px] bg-gray-200 mx-1"></div>

            <!-- Rating Filter -->
            <div class="flex items-center gap-2">
              <span class="text-gray-500 text-xs font-medium">评价:</span>
              <a-select
                v-model:value="selectedRating"
                style="width: 110px"
                placeholder="全部"
                @change="handleFilterChange"
                :options="ratingOptions"
                size="small"
                class="custom-select"
              />
            </div>

            <div class="h-4 w-[1px] bg-gray-200 mx-1"></div>

            <!-- Public Filter -->
            <div class="flex items-center gap-2">
              <span class="text-gray-500 text-xs font-medium">状态:</span>
              <a-select
                v-model:value="selectedPublic"
                style="width: 110px"
                placeholder="全部"
                @change="handleFilterChange"
                :options="publicOptions"
                size="small"
                class="custom-select"
              />
            </div>

            <div class="h-4 w-[1px] bg-gray-200 mx-1"></div>

            <!-- Worker Filter -->
            <div class="flex items-center gap-2">
              <span class="text-gray-500 text-xs font-medium">节点:</span>
              <a-select
                v-model:value="selectedWorker"
                style="width: 120px"
                placeholder="全部节点"
                @change="handleFilterChange"
                :options="workerOptions"
                size="small"
                show-search
                allow-clear
                option-filter-prop="label"
                class="custom-select"
              />
            </div>

            <a-button 
              v-if="selectedTypes.length > 0 || selectedRating !== null || selectedPublic !== null || selectedWorker !== null"
              size="small" 
              type="text" 
              danger 
              class="flex items-center gap-1 ml-1 hover:bg-red-50"
              @click="resetFilters"
            >
              <template #icon><close-circle-filled /></template>
              重置
            </a-button>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <a-button @click="refreshData" :loading="loading" type="text" class="flex items-center gap-1 text-gray-500 hover:text-blue-600">
            <template #icon><reload-outlined /></template>
            刷新
          </a-button>
        </div>
      </div>
    </div>

    <a-table
      :columns="columns"
      :data-source="history"
      :loading="loading"
      :pagination="{
        current: currentPage,
        pageSize: pageSize,
        total: total,
        showSizeChanger: false,
        showTotal: (total) => `共 ${total} 条`
      }"
      @change="handleTableChange"
      row-key="id"
      class="flex-1 overflow-hidden"
      :scroll="{ y: 'calc(100vh - 350px)' }"
    >
      <template #bodyCell="{ column, record }">
        <!-- Time -->
        <template v-if="column.key === 'created_at'">
          <span class="text-xs text-gray-500">{{ formatDate(record.created_at) }}</span>
        </template>

        <!-- User -->
        <template v-else-if="column.key === 'user'">
          <div class="flex items-center gap-2">
            <a-avatar size="small" class="bg-blue-100 text-blue-600">
              <template #icon><UserOutlined /></template>
            </a-avatar>
            <div class="flex flex-col">
              <span class="text-sm font-medium text-gray-700">
                {{ record.full_name || record.username || 'Unknown' }}
              </span>
              <span class="text-xs text-gray-400">ID: {{ record.user_id }}</span>
            </div>
          </div>
        </template>

        <!-- Type -->
        <template v-else-if="column.key === 'type'">
          <a-tag :color="record.type === 'image' ? 'blue' : 'orange'">
            {{ getTaskTypeLabel(record.type) }}
          </a-tag>
        </template>

        <!-- Source -->
        <template v-else-if="column.key === 'source'">
          <a-tag :color="record.source === 'web' ? 'green' : 'orange'" class="text-xs w-14 text-center">
            {{ record.source === 'web' ? 'Web' : 'Bot' }}
          </a-tag>
        </template>

        <!-- Worker ID -->
        <template v-else-if="column.key === 'worker_id'">
          <a-tag v-if="record.worker_id" color="purple" class="text-xs">
            {{ record.worker_id }}
          </a-tag>
          <span v-else class="text-xs text-gray-400">-</span>
        </template>

        <!-- Input -->
        <template v-else-if="column.key === 'input'">
          <div class="flex flex-wrap gap-2 py-1">
             <template v-if="record.input_file">
                <MediaItem 
                  v-for="(url, index) in (record.input_file_url || '').split('|')" 
                  :key="index"
                  :file="record.input_file.split('|')[index]"
                  :url="url"
                  size="w-16 h-16"
                />
             </template>
             <span v-else class="text-xs text-gray-400">无</span>
          </div>
        </template>

        <!-- Output -->
        <template v-else-if="column.key === 'output'">
          <div class="py-1">
            <template v-if="record.output_file">
              <MediaItem 
                :file="record.output_file"
                :url="record.output_file_url"
                size="w-16 h-16"
              />
            </template>
            <span v-else class="text-xs text-gray-400">生成中/失败</span>
          </div>
        </template>

        <!-- Prompt -->
        <template v-else-if="column.key === 'prompt'">
          <template v-if="record.prompt">
            <div class="flex flex-col gap-1">
              <div v-if="record.prompt.startsWith('[')" class="flex flex-wrap gap-1">
                <a-tag v-if="record.prompt.match(/^\[(.*?)\]/)" color="blue" class="text-[10px] m-0 px-1.5 py-0 border-blue-200 bg-blue-50/50">
                  {{ record.prompt.match(/^\[(.*?)\]/)[1] }}
                </a-tag>
              </div>
              <a-tooltip :title="record.prompt.replace(/^\[.*?\]\s*/, '')" placement="topLeft" overlayClassName="max-w-md">
                <div class="truncate max-w-xs text-xs text-gray-600 cursor-pointer hover:text-blue-600 transition-colors">
                  {{ record.prompt.replace(/^\[.*?\]\s*/, '') }}
                </div>
              </a-tooltip>
            </div>
          </template>
          <span v-else class="text-xs text-gray-400">无</span>
        </template>
      </template>
    </a-table>
  </div>
</template>

<style scoped>
:deep(.ant-table-wrapper) {
  height: 100%;
}
:deep(.ant-spin-nested-loading) {
  height: 100%;
}
:deep(.ant-spin-container) {
  height: 100%;
  display: flex;
  flex-direction: column;
}
:deep(.ant-table) {
  flex: 1;
}
</style>
