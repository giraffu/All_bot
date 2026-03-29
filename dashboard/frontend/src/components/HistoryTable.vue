<script setup>
import { ref, onMounted } from 'vue'
import { fetchHistoryAll } from '../api/api'
import { getFileUrl, formatDate } from '../utils/helpers'
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
  'blowjob': '口交黑人',
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
  'unknown': '未知类型'
};

const typeOptions = [
  { label: '自定义视频', value: 'custom_video' },
  { label: '自由P图', value: 'image' },
  { label: '快速换脸', value: 'face_swap' },
  { label: '快速脱衣', value: 'undress' },
  { label: '动图传教士', value: 'perfect_video_insert' },
  { label: '快速自慰', value: 'masturbation' },
  { label: '特写口交', value: 'closeup_blowjob' },
  { label: '动图后入', value: 'doggy_style' },
  { label: '口交黑人', value: 'blowjob' },
  { label: '脱衣吐舌', value: 'undress_tongue' },
  { label: '快速抽插', value: 'penetration' },
  { label: '文生图', value: 'text_to_image' },
  { label: '动图做爱', value: 'fuck' },
  { label: '动图露奶', value: 'face_show' },
  { label: '动图吐舌', value: 'face_tongue' },
  { label: '专业视频', value: 'video_pro' },
  { label: '视频脱衣', value: 'video_undress' },
  { label: '随机换脸', value: 'random_faceswap' },
  { label: '视频生成', value: 'video' },
  { label: '模板共建', value: 'template_contribute' }
];

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
    const data = await fetchHistoryAll(page, pageSize.value, typeParam, selectedRating.value, selectedPublic.value)
    history.value = data.items
    total.value = data.total
    currentPage.value = page
  } catch (err) {
    console.error('Failed to load history:', err)
  } finally {
    loading.value = false
  }
}

const handleFilterChange = () => {
  loadData(1)
}

const resetFilters = () => {
  selectedTypes.value = []
  selectedRating.value = null
  selectedPublic.value = null
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

            <a-button 
              v-if="selectedTypes.length > 0 || selectedRating !== null || selectedPublic !== null"
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
            {{ typeMapping[record.type] || record.type }}
          </a-tag>
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
          <a-tooltip v-if="record.prompt" :title="record.prompt" placement="topLeft" overlayClassName="max-w-md">
             <div class="truncate max-w-xs text-xs text-gray-600 cursor-pointer hover:text-blue-600 transition-colors">
               {{ record.prompt }}
             </div>
          </a-tooltip>
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
