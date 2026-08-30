<script setup>
import { ref, onBeforeUnmount, onMounted } from 'vue'
import { fetchHistoryAll, fetchWorkerList } from '../api/api'
import { formatDate } from '../utils/helpers'
import { getTaskTypeLabel, TASK_TYPE_OPTIONS } from '../constants/taskTypes'
import { buildHistoryInputMedia } from '../utils/historyInputMedia'
import {
  HISTORY_SOURCE_OPTIONS,
  getHistorySourceColor,
  getHistorySourceLabel,
} from '../constants/historySources'
import MediaItem from './MediaItem.vue'
import { 
  UserOutlined,
  ReloadOutlined,
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
const selectedSource = ref(null)
const usernameInput = ref('')
const selectedUsername = ref(null)
const workerOptions = ref([{ label: '全部节点', value: null }])
const sourceOptions = HISTORY_SOURCE_OPTIONS
let activeHistoryRequest = null

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
  activeHistoryRequest?.abort()
  const requestController = new AbortController()
  activeHistoryRequest = requestController
  loading.value = true
  try {
    const typeParam = selectedTypes.value.length > 0 ? selectedTypes.value.join(',') : null
    const data = await fetchHistoryAll(
      page,
      pageSize.value,
      typeParam,
      selectedRating.value,
      selectedPublic.value,
      selectedWorker.value,
      selectedSource.value,
      selectedUsername.value,
      { signal: requestController.signal },
    )
    if (activeHistoryRequest !== requestController) return
    history.value = data.items
    total.value = data.total
    currentPage.value = page
  } catch (err) {
    if (!requestController.signal.aborted) {
      console.error('Failed to load history:', err)
    }
  } finally {
    if (activeHistoryRequest === requestController) {
      loading.value = false
      activeHistoryRequest = null
    }
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

const handleUsernameSearch = (value) => {
  const normalizedValue = value.trim().replace(/^@/, '')
  usernameInput.value = normalizedValue
  selectedUsername.value = normalizedValue || null
  loadData(1)
}

const handleUsernameInputChange = (event) => {
  if (event.target.value === '' && selectedUsername.value !== null) {
    selectedUsername.value = null
    loadData(1)
  }
}

const resetFilters = () => {
  selectedTypes.value = []
  selectedRating.value = null
  selectedPublic.value = null
  selectedWorker.value = null
  selectedSource.value = null
  usernameInput.value = ''
  selectedUsername.value = null
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
    width: 170,
  },
  {
    title: '来源',
    dataIndex: 'source',
    key: 'source',
    width: 180,
  },
  {
    title: '生成节点',
    dataIndex: 'worker_id',
    key: 'worker_id',
    width: 190,
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

onBeforeUnmount(() => {
  activeHistoryRequest?.abort()
})
</script>

<template>
  <div
    data-testid="history-table-shell"
    class="history-table-shell h-full min-h-0 min-w-0 flex flex-col bg-white rounded-xl shadow-sm border p-3 sm:p-4 xl:p-6"
  >
    <div class="mb-3 flex shrink-0 flex-col gap-3 xl:mb-4 xl:flex-row xl:items-center">
      <div class="flex items-center justify-between gap-3 xl:shrink-0">
        <h2 class="m-0 text-lg font-bold text-gray-800 sm:text-xl">历史生成记录</h2>
        <a-button
          @click="refreshData"
          :loading="loading"
          type="text"
          class="flex items-center gap-1 text-gray-500 hover:text-blue-600 xl:hidden"
        >
          <template #icon><reload-outlined /></template>
          刷新
        </a-button>
      </div>

      <div class="flex min-w-0 flex-1 items-center gap-3">
        <!-- Filters Group -->
        <div
          data-testid="history-filter-strip"
          class="history-filter-strip flex min-w-0 flex-1 items-center gap-3 overflow-x-auto rounded-xl border border-gray-100 bg-gray-50 px-3 py-2 shadow-sm"
        >
            <!-- Username Filter -->
            <div class="flex shrink-0 items-center gap-2">
              <span class="text-gray-500 text-xs font-medium">用户名:</span>
              <a-input-search
                v-model:value="usernameInput"
                data-testid="history-username-filter"
                style="width: 160px"
                placeholder="输入完整用户名"
                size="small"
                allow-clear
                @change="handleUsernameInputChange"
                @search="handleUsernameSearch"
              />
            </div>

            <div class="h-4 w-[1px] shrink-0 bg-gray-200 mx-1"></div>

            <!-- Multiple Type Filter -->
            <div class="flex shrink-0 items-center gap-2">
              <span class="text-gray-500 text-xs font-medium">类型:</span>
              <a-select
                v-model:value="selectedTypes"
                mode="multiple"
                data-testid="history-type-filter"
                style="min-width: 240px; max-width: 360px"
                placeholder="全部类型"
                @change="handleFilterChange"
                :options="typeOptions"
                size="small"
                show-search
                allow-clear
                option-filter-prop="label"
                max-tag-count="responsive"
                :popup-match-select-width="300"
                class="custom-select"
              />
            </div>

            <div class="h-4 w-[1px] shrink-0 bg-gray-200 mx-1"></div>

            <!-- Rating Filter -->
            <div class="flex shrink-0 items-center gap-2">
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

            <div class="h-4 w-[1px] shrink-0 bg-gray-200 mx-1"></div>

            <!-- Public Filter -->
            <div class="flex shrink-0 items-center gap-2">
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

            <div class="h-4 w-[1px] shrink-0 bg-gray-200 mx-1"></div>

            <!-- Worker Filter -->
            <div class="flex shrink-0 items-center gap-2">
              <span class="text-gray-500 text-xs font-medium">节点:</span>
              <a-select
                v-model:value="selectedWorker"
                data-testid="history-worker-filter"
                style="width: 190px"
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

            <div class="h-4 w-[1px] shrink-0 bg-gray-200 mx-1"></div>

            <!-- Source Filter -->
            <div class="flex shrink-0 items-center gap-2">
              <span class="text-gray-500 text-xs font-medium">来源:</span>
              <a-select
                v-model:value="selectedSource"
                data-testid="history-source-filter"
                style="width: 180px"
                placeholder="全部来源"
                @change="handleFilterChange"
                :options="sourceOptions"
                size="small"
                class="custom-select"
              />
            </div>

            <a-button 
              v-if="selectedUsername !== null || selectedTypes.length > 0 || selectedRating !== null || selectedPublic !== null || selectedWorker !== null || selectedSource !== null"
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

        <div class="hidden shrink-0 items-center gap-2 xl:flex">
          <a-button
            @click="refreshData"
            :loading="loading"
            type="text"
            class="flex items-center gap-1 text-gray-500 hover:text-blue-600"
          >
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
        responsive: true,
        showLessItems: true,
        showTotal: (total) => `共 ${total} 条`
      }"
      @change="handleTableChange"
      row-key="id"
      class="history-results min-h-0 min-w-0 flex-1 overflow-hidden"
      :scroll="{ x: 1350, y: 'calc(100dvh - 350px)' }"
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
          <a-tag
            :color="record.type === 'image' ? 'blue' : 'orange'"
            class="max-w-[155px] overflow-hidden text-ellipsis whitespace-nowrap"
            :title="getTaskTypeLabel(record.type)"
          >
            {{ getTaskTypeLabel(record.type) }}
          </a-tag>
        </template>

        <!-- Source -->
        <template v-else-if="column.key === 'source'">
          <a-tag :color="getHistorySourceColor(record.source)" class="text-xs whitespace-nowrap text-center">
            {{ getHistorySourceLabel(record.source) }}
          </a-tag>
        </template>

        <!-- Worker ID -->
        <template v-else-if="column.key === 'worker_id'">
          <a-tag
            v-if="record.worker_id"
            color="purple"
            class="text-xs max-w-[175px] overflow-hidden text-ellipsis whitespace-nowrap"
            :title="record.worker_id"
          >
            {{ record.worker_id }}
          </a-tag>
          <span v-else class="text-xs text-gray-400">-</span>
        </template>

        <!-- Input -->
        <template v-else-if="column.key === 'input'">
          <div class="flex flex-wrap gap-2 py-1">
             <template v-if="record.input_file">
                <MediaItem 
                  v-for="(media, index) in buildHistoryInputMedia(record)"
                  :key="`${media.file}-${index}`"
                  :file="media.file"
                  :url="media.url"
                  :preview-url="media.previewUrl"
                  :label="media.label"
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
                :preview-url="record.output_file_preview_url || ''"
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
:deep(.history-filter-strip) {
  scrollbar-width: thin;
}

:deep(.ant-table-wrapper) {
  height: 100%;
  min-height: 0;
}
:deep(.ant-spin-nested-loading) {
  height: 100%;
  min-height: 0;
}
:deep(.ant-spin-container) {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
:deep(.ant-table) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
:deep(.ant-table-container) {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
}
:deep(.ant-table-header) {
  flex: none;
}
:deep(.ant-table-body) {
  min-height: 0;
  max-height: none !important;
  flex: 1;
}
:deep(.ant-pagination) {
  flex: none;
  margin: 12px 0 0;
}

@media (max-width: 767px) {
  :deep(.ant-pagination) {
    justify-content: center;
    margin-top: 8px;
  }

  :deep(.ant-pagination-total-text) {
    display: none;
  }
}
</style>
