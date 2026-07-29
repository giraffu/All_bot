<script setup lang="ts">
import { computed, h, onMounted, ref } from 'vue'
import message from 'ant-design-vue/es/message'
import Modal from 'ant-design-vue/es/modal'
import {
  EyeOutlined,
  ExclamationCircleOutlined,
  PictureOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SearchOutlined,
  StopOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'
import {
  apiBaseUrl,
  banGalleryUserSubmissionsAndTakedown,
  fetchGalleryReports,
  resolveGalleryReport,
  takedownGalleryReport,
} from '../api/api'
import { formatDate } from '../utils/helpers'

interface GalleryReportItem {
  id: number
  post_id: number | null
  post_task_id: string | null
  post_is_active: boolean | null
  post_author_user_id: number | null
  post_author_name: string | null
  reporter_user_id: number | null
  reporter_name: string | null
  reason: 'children' | 'gore' | 'gross' | 'other'
  status: 'pending' | 'resolved'
  created_at: string | null
  resolved_at: string | null
  resolution_action: string | null
  media_type: 'image' | 'video' | null
  media_url: string | null
  prompt: string | null
}

interface PaginationState {
  current: number
  pageSize: number
  total: number
}

interface PreviewMedia {
  type: 'image' | 'video'
  url: string
}

const loading = ref(false)
const reports = ref<GalleryReportItem[]>([])
const actionLoading = ref<Record<number, string | undefined>>({})
const previewVisible = ref(false)
const previewMedia = ref<PreviewMedia | null>(null)
const pagination = ref<PaginationState>({
  current: 1,
  pageSize: 20,
  total: 0,
})

const filterStatus = ref<'pending' | 'resolved' | 'all'>('pending')
const filterReason = ref<'all' | GalleryReportItem['reason']>('all')
const filterPostId = ref<number | undefined>(undefined)

const statusOptions = [
  { label: '待处理', value: 'pending' },
  { label: '已处理', value: 'resolved' },
  { label: '全部', value: 'all' },
]

const reasonOptions = [
  { label: '全部', value: 'all' },
  { label: '儿童', value: 'children' },
  { label: '血腥', value: 'gore' },
  { label: '恶心', value: 'gross' },
  { label: '其他', value: 'other' },
]

const columns = computed(() => [
  {
    title: '举报ID',
    dataIndex: 'id',
    width: 90,
  },
  {
    title: '作品',
    key: 'post',
    width: 220,
  },
  {
    title: '原因',
    dataIndex: 'reason',
    width: 110,
  },
  {
    title: '举报人',
    key: 'reporter',
    width: 150,
  },
  {
    title: '作者',
    key: 'author',
    width: 150,
  },
  {
    title: '提示词',
    dataIndex: 'prompt',
    width: 280,
  },
  {
    title: '状态',
    dataIndex: 'status',
    width: 130,
  },
  {
    title: '时间',
    key: 'time',
    width: 180,
  },
  {
    title: '操作',
    key: 'action',
    width: 230,
    fixed: 'right',
  },
])

const getReportRowKey = (record: GalleryReportItem) => record.id

const getReasonLabel = (reason: GalleryReportItem['reason'] | string | null) => {
  return reasonOptions.find(option => option.value === reason)?.label || '未知'
}

const getStatusLabel = (status: GalleryReportItem['status']) =>
  status === 'pending' ? '待处理' : '已处理'

const getResolutionLabel = (action: string | null) => {
  if (action === 'ban_and_takedown') return '封禁并下架'
  if (action === 'takedown') return '已下架'
  if (action === 'already_inactive') return '作品已下架'
  if (action === 'post_missing') return '作品不存在'
  if (action === 'manual_resolve') return '人工处理'
  return action || '-'
}

const getUserMeta = (userId: number | null) => (userId ? `ID ${userId}` : '-')

const getMediaUrl = (url: string | null) => {
  if (!url) return ''
  if (url.startsWith('http')) return url
  return `${apiBaseUrl}${url}`
}

const showPreview = (record: GalleryReportItem) => {
  if (!record.media_url || !record.media_type) {
    message.warning('媒体文件不可用或已失效')
    return
  }

  previewMedia.value = {
    type: record.media_type,
    url: getMediaUrl(record.media_url),
  }
  previewVisible.value = true
}

const normalizePostId = (value: number | null | undefined) => {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue) || numericValue < 1) {
    return undefined
  }
  return Math.floor(numericValue)
}

const buildParams = (page = pagination.value.current) => ({
  page,
  page_size: pagination.value.pageSize,
  status: filterStatus.value,
  reason: filterReason.value === 'all' ? undefined : filterReason.value,
  post_id: normalizePostId(filterPostId.value),
})

const loadReports = async (page = pagination.value.current) => {
  try {
    loading.value = true
    const res = await fetchGalleryReports(buildParams(page))
    reports.value = res.items
    pagination.value = {
      ...pagination.value,
      current: res.page,
      pageSize: res.page_size,
      total: res.total,
    }
  } catch (error: any) {
    message.error(`加载举报失败: ${error.response?.data?.detail || error.message}`)
  } finally {
    loading.value = false
  }
}

const handleTableChange = (pag: { current?: number; pageSize?: number }) => {
  pagination.value = {
    ...pagination.value,
    current: pag.current || 1,
    pageSize: pag.pageSize || pagination.value.pageSize,
  }
  void loadReports(pagination.value.current)
}

const applyFilters = () => {
  pagination.value = {
    ...pagination.value,
    current: 1,
  }
  void loadReports(1)
}

const resetFilters = () => {
  filterStatus.value = 'pending'
  filterReason.value = 'all'
  filterPostId.value = undefined
  applyFilters()
}

const markResolved = async (record: GalleryReportItem) => {
  try {
    actionLoading.value[record.id] = 'resolve'
    await resolveGalleryReport(record.id)
    message.success('举报已标记处理')
    await loadReports(pagination.value.current)
  } catch (error: any) {
    message.error(`处理失败: ${error.response?.data?.detail || error.message}`)
  } finally {
    actionLoading.value[record.id] = undefined
  }
}

const confirmBanAndTakedown = (record: GalleryReportItem) => {
  const authorUserId = record.post_author_user_id
  if (!authorUserId) {
    message.warning('该作品缺少作者用户 ID，无法执行用户级操作')
    return
  }

  const targetName = record.post_author_name || `用户 ${authorUserId}`
  Modal.confirm({
    title: '确认封禁并下架该用户所有投稿?',
    icon: h(ExclamationCircleOutlined),
    content: `将禁止用户 ${targetName} 后续投稿，并下架该用户当前所有广场投稿。此操作不会删除文件或历史记录。`,
    okText: '封禁并下架',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        actionLoading.value[record.id] = 'ban_and_takedown'
        const res = await banGalleryUserSubmissionsAndTakedown(authorUserId)
        message.success(
          `已封禁用户 ${authorUserId}，下架 ${res.affected_posts || 0} 条投稿，处理 ${res.resolved_reports || 0} 条举报`,
        )
        await loadReports(pagination.value.current)
      } catch (error: any) {
        message.error(`操作失败: ${error.response?.data?.detail || error.message}`)
        throw error
      } finally {
        actionLoading.value[record.id] = undefined
      }
    },
  })
}

const confirmSingleTakedown = (record: GalleryReportItem) => {
  if (!record.post_id || record.post_is_active === false) {
    message.warning('当前作品已下架或不存在')
    return
  }

  Modal.confirm({
    title: '确认仅下架当前这条内容?',
    icon: h(ExclamationCircleOutlined),
    content: `只下架作品 #${record.post_id} 并处理该作品的待处理举报；不会封禁用户，也不会影响该用户的其他投稿。`,
    okText: '仅下架此条',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        actionLoading.value[record.id] = 'single_takedown'
        await takedownGalleryReport(record.id)
        message.success(
          `已下架作品 ${record.post_id}，未封禁用户 ${record.post_author_user_id || '-'}`,
        )
        await loadReports(pagination.value.current)
      } catch (error: any) {
        message.error(`操作失败: ${error.response?.data?.detail || error.message}`)
        throw error
      } finally {
        actionLoading.value[record.id] = undefined
      }
    },
  })
}

onMounted(() => {
  void loadReports(1)
})
</script>

<template>
  <div class="h-full flex flex-col">
    <div class="mb-4 flex flex-wrap items-center justify-between gap-4">
      <div class="flex flex-wrap items-center gap-3">
        <h2 class="m-0 text-lg font-semibold flex items-center gap-2">
          <warning-outlined class="text-amber-500" />
          举报管理
        </h2>

        <a-divider type="vertical" class="h-6" />

        <div class="flex items-center gap-2">
          <span class="text-gray-500">状态:</span>
          <a-select
            v-model:value="filterStatus"
            :options="statusOptions"
            class="w-32"
            @change="applyFilters"
          />
        </div>

        <div class="flex items-center gap-2">
          <span class="text-gray-500">原因:</span>
          <a-select
            v-model:value="filterReason"
            :options="reasonOptions"
            class="w-32"
            @change="applyFilters"
          />
        </div>

        <div class="flex items-center gap-2">
          <span class="text-gray-500">作品 ID:</span>
          <a-input-number
            v-model:value="filterPostId"
            :min="1"
            :precision="0"
            :controls="false"
            placeholder="全部"
            class="w-32"
            @pressEnter="applyFilters"
          />
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <a-button @click="resetFilters" :disabled="loading">重置</a-button>
        <a-button @click="applyFilters" :loading="loading">
          <template #icon><search-outlined /></template>
          筛选
        </a-button>
        <a-button type="primary" @click="() => loadReports(1)" :loading="loading">
          <template #icon><reload-outlined /></template>
          刷新数据
        </a-button>
      </div>
    </div>

    <div class="flex-1 min-h-0 overflow-hidden rounded-lg border bg-white">
      <a-table
        :columns="columns"
        :data-source="reports"
        :row-key="getReportRowKey"
        :pagination="pagination"
        :loading="loading"
        :scroll="{ y: 'calc(100vh - 290px)', x: 1380 }"
        size="middle"
        class="h-full"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'post'">
            <div class="flex items-center gap-3 min-w-[200px]">
              <button
                v-if="record.media_url && record.media_type"
                type="button"
                class="w-14 h-14 rounded bg-gray-100 border overflow-hidden flex items-center justify-center shrink-0 cursor-zoom-in hover:border-blue-400 transition-colors relative group"
                :aria-label="`查看作品 ${record.post_id || record.id} ${record.media_type === 'video' ? '视频' : '图片'}`"
                @click="showPreview(record)"
              >
                  <img
                    v-if="record.media_type === 'image'"
                    :src="getMediaUrl(record.media_url)"
                    :alt="`作品 ${record.post_id || record.id} 缩略图`"
                    class="w-full h-full object-cover"
                  />
                  <video
                    v-else
                    :src="getMediaUrl(record.media_url)"
                    class="w-full h-full object-cover"
                  />
                <span class="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
                  <play-circle-outlined v-if="record.media_type === 'video'" class="text-white text-xl" />
                  <picture-outlined v-else class="text-white text-xl" />
                </span>
              </button>
              <div v-else class="w-14 h-14 rounded bg-gray-100 border overflow-hidden flex items-center justify-center shrink-0">
                <eye-outlined class="text-gray-300" />
              </div>
              <div class="min-w-0 text-sm leading-6">
                <div class="font-medium text-gray-900">
                  {{ record.post_id ? `#${record.post_id}` : '作品已删除' }}
                </div>
                <div class="truncate text-xs text-gray-500">
                  task: {{ record.post_task_id || '-' }}
                </div>
                <a-tag :color="record.post_is_active ? 'blue' : 'default'" class="mt-1">
                  {{ record.post_is_active ? '展示中' : '已下架/缺失' }}
                </a-tag>
              </div>
            </div>
          </template>

          <template v-else-if="column.dataIndex === 'reason'">
            <a-tag color="warning">{{ getReasonLabel(record.reason) }}</a-tag>
          </template>

          <template v-else-if="column.key === 'reporter'">
            <div class="text-sm leading-6">
              <div class="font-medium text-gray-900">{{ record.reporter_name || 'Unknown' }}</div>
              <div class="text-xs text-gray-500">{{ getUserMeta(record.reporter_user_id) }}</div>
            </div>
          </template>

          <template v-else-if="column.key === 'author'">
            <div class="text-sm leading-6">
              <div class="font-medium text-gray-900">{{ record.post_author_name || 'Unknown' }}</div>
              <div class="text-xs text-gray-500">{{ getUserMeta(record.post_author_user_id) }}</div>
            </div>
          </template>

          <template v-else-if="column.dataIndex === 'prompt'">
            <div class="line-clamp-4 whitespace-pre-wrap break-words text-sm text-gray-700" :title="record.prompt || ''">
              {{ record.prompt || '-' }}
            </div>
          </template>

          <template v-else-if="column.dataIndex === 'status'">
            <div class="flex flex-col gap-1">
              <a-tag :color="record.status === 'pending' ? 'red' : 'success'">
                {{ getStatusLabel(record.status) }}
              </a-tag>
              <span v-if="record.status === 'resolved'" class="text-xs text-gray-500">
                {{ getResolutionLabel(record.resolution_action) }}
              </span>
            </div>
          </template>

          <template v-else-if="column.key === 'time'">
            <div class="text-sm leading-6">
              <div>{{ formatDate(record.created_at) }}</div>
              <div v-if="record.resolved_at" class="text-xs text-gray-500">
                处理: {{ formatDate(record.resolved_at) }}
              </div>
            </div>
          </template>

          <template v-else-if="column.key === 'action'">
            <div class="flex flex-wrap gap-2 w-[250px]">
              <a-popconfirm
                title="确认标记这条举报为已处理？"
                ok-text="确认"
                cancel-text="取消"
                @confirm="markResolved(record)"
              >
                <a-button
                  size="small"
                  :disabled="record.status === 'resolved'"
                  :loading="actionLoading[record.id] === 'resolve'"
                >
                  标记处理
                </a-button>
              </a-popconfirm>

              <a-button
                size="small"
                danger
                :disabled="record.status === 'resolved' || !record.post_id || record.post_is_active === false"
                :loading="actionLoading[record.id] === 'single_takedown'"
                @click="confirmSingleTakedown(record)"
              >
                仅下架此条
              </a-button>

              <a-button
                size="small"
                danger
                :disabled="record.status === 'resolved' || !record.post_author_user_id"
                :loading="actionLoading[record.id] === 'ban_and_takedown'"
                @click="confirmBanAndTakedown(record)"
              >
                <template #icon><stop-outlined /></template>
                封禁并下架
              </a-button>
            </div>
          </template>
        </template>
      </a-table>
    </div>

    <a-modal
      v-model:open="previewVisible"
      title="媒体预览"
      :footer="null"
      width="min(900px, 92vw)"
      centered
      destroy-on-close
    >
      <div class="flex justify-center items-center bg-gray-100 rounded-lg p-2 min-h-[300px]">
        <img
          v-if="previewMedia?.type === 'image'"
          :src="previewMedia.url"
          alt="举报作品大图预览"
          class="max-w-full max-h-[75vh] object-contain rounded shadow-sm"
        />
        <video
          v-else-if="previewMedia?.type === 'video'"
          :src="previewMedia.url"
          controls
          autoplay
          loop
          class="max-w-full max-h-[75vh] rounded shadow-sm"
        />
      </div>
    </a-modal>
  </div>
</template>
