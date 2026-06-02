<script setup>
import { ref, onMounted, h } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  ExclamationCircleOutlined,
  PictureOutlined,
  PlayCircleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  CopyOutlined,
  StopOutlined,
  UserOutlined
} from '@ant-design/icons-vue'
import {
  banGalleryUserSubmissionsAndTakedown,
  fetchGalleryPosts,
  updateGalleryPost,
  deleteGalleryPost,
  apiBaseUrl
} from '../api/api'
import { copyTextWithFallback } from '../utils/helpers'

const props = defineProps({
  onOpenCommentsTab: {
    type: Function,
    default: undefined
  }
})

const loading = ref(false)
const posts = ref([])
const pagination = ref({
  current: 1,
  pageSize: 10,
  total: 0
})

const copyToClipboard = async (text) => {
  if (!text) return

  const copied = await copyTextWithFallback(text)
  if (copied) {
    message.success('提示词已复制')
  } else {
    message.error('复制失败，浏览器可能拦截了该操作')
  }
}

// Filters
const filterActive = ref(undefined)
const filterTaskType = ref('all')
const filterSort = ref('created_at')

const sortOptions = [
  { label: '最新时间', value: 'created_at' },
  { label: '最多点赞', value: 'likes' },
  { label: '最多点踩', value: 'dislikes' },
  { label: '绝对最多点赞', value: 'absolute_likes' },
  { label: '绝对最多点踩', value: 'absolute_dislikes' },
  { label: '最多应用', value: 'applied' }
]

const taskTypeOptions = [
  { label: '全部', value: 'all' },
  { label: '高级图生视频', value: 'ltx_video' },
  { label: '图生视频 V2', value: 'wan22_video_v2' },
  { label: '幻想换脸', value: 'i2i_pro' },
  { label: '局部重绘', value: 'edit' },
  { label: '动态视频', value: 'custom_video' },
  { label: '视频风格化', value: 'video_lora' },
  { label: '图生图', value: 'img2img' },
  { label: '文生图', value: 'txt2img' },
  { label: '视频换脸', value: 'face_video' },
  { label: '图片换脸', value: 'face_swap' }
]

const statusOptions = [
  { label: '全部', value: undefined },
  { label: '已上架', value: true },
  { label: '已下架', value: false }
]

// Edit Modal
const editModalVisible = ref(false)
const editingPost = ref(null)
const editForm = ref({
  likes_count: 0,
  dislikes_count: 0,
  applied_count: 0,
  comments_count: 0,
  tags: '[]'
})
const submitLoading = ref(false)

// Preview Modal
const previewVisible = ref(false)
const previewMedia = ref(null)

const getTaskTypeName = (type) => {
  const option = taskTypeOptions.find(opt => opt.value === type)
  return option ? option.label : type
}

const getAuthorDisplayName = (record) => {
  return (
    record.author_name ||
    record.full_name ||
    record.username ||
    (record.user_id ? `用户 ${record.user_id}` : '未知用户')
  )
}

const getAuthorMeta = (record) => {
  const displayName = getAuthorDisplayName(record)
  const parts = []
  if (record.username && record.username !== displayName) {
    parts.push(`@${record.username}`)
  }
  if (record.user_id) {
    parts.push(`ID ${record.user_id}`)
  }
  return parts.join(' / ')
}

const columns = [
  {
    title: '预览',
    key: 'preview',
    width: 120,
    align: 'center'
  },
  {
    title: '投稿用户',
    key: 'author',
    width: 170,
  },
  {
    title: '具体类型',
    key: 'task_type',
    width: 120,
  },
  {
    title: '规格',
    key: 'specs',
    width: 120,
  },
  {
    title: '提示词 (Prompt)',
    dataIndex: 'prompt',
    width: 300,
  },
  {
    title: '状态',
    dataIndex: 'is_active',
    width: 100,
  },
  {
    title: '数据统计',
    key: 'stats',
    width: 200,
  },
  {
    title: '操作',
    key: 'action',
    width: 320,
    fixed: 'right'
  }
]

const loadData = async (page = pagination.value.current) => {
  try {
    loading.value = true
    const params = {
      page: page,
      page_size: pagination.value.pageSize,
    }
    
    if (filterActive.value !== undefined) {
      params.is_active = filterActive.value
    }
    if (filterTaskType.value !== 'all') {
      params.task_type = filterTaskType.value
    }
    if (filterSort.value && filterSort.value !== 'created_at') {
      params.sort_by = filterSort.value
    }

    const res = await fetchGalleryPosts(params)
    posts.value = res.items
    pagination.value = {
      ...pagination.value,
      current: res.page,
      total: res.total
    }
  } catch (error) {
    console.error('Error loading gallery posts:', error)
    message.error('加载广场内容失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

const handleTableChange = (pag) => {
  loadData(pag.current)
}

const onFilterChange = () => {
  loadData(1)
}

const toggleStatus = async (record) => {
  try {
    const newStatus = !record.is_active
    await updateGalleryPost(record.id, { is_active: newStatus })
    message.success(`已${newStatus ? '上架' : '下架'}该内容`)
    record.is_active = newStatus
  } catch (error) {
    message.error('操作失败: ' + (error.response?.data?.detail || error.message))
  }
}

const editPost = (record) => {
  editingPost.value = record
  editForm.value = {
    likes_count: record.likes_count,
    dislikes_count: record.dislikes_count,
    applied_count: record.applied_count,
    comments_count: record.comments_count || 0,
    tags: record.tags
  }
  editModalVisible.value = true
}

const handleEditSubmit = async () => {
  try {
    submitLoading.value = true
    // Validate JSON
    try {
      JSON.parse(editForm.value.tags)
    } catch (e) {
      message.error('标签格式必须是有效的JSON数组字符串，例如: ["#标签1", "#标签2"]')
      return
    }

    await updateGalleryPost(editingPost.value.id, {
      likes_count: editForm.value.likes_count,
      dislikes_count: editForm.value.dislikes_count,
      applied_count: editForm.value.applied_count,
      comments_count: editForm.value.comments_count,
      tags: editForm.value.tags
    })
    
    message.success('修改成功')
    editModalVisible.value = false
    loadData()
  } catch (error) {
    message.error('修改失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    submitLoading.value = false
  }
}

const openCommentsManager = (record) => {
  props.onOpenCommentsTab?.(record.id)
}

const confirmDelete = (record) => {
  Modal.confirm({
    title: '确认删除该投稿?',
    icon: h(ExclamationCircleOutlined),
    content: `删除后不可恢复 (ID: ${record.id})`,
    okText: '确认删除',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        await deleteGalleryPost(record.id)
        message.success('删除成功')
        loadData()
      } catch (error) {
        message.error('删除失败: ' + (error.response?.data?.detail || error.message))
      }
    },
  })
}

const confirmBanAndTakedown = (record) => {
  if (!record.user_id) {
    message.warning('该投稿缺少用户 ID，无法执行用户级操作')
    return
  }

  const targetName = getAuthorDisplayName(record)
  Modal.confirm({
    title: '确认封禁并下架该用户所有投稿?',
    icon: h(ExclamationCircleOutlined),
    content: record.is_submission_banned
      ? `用户 ${targetName} 已处于投稿封禁状态。本次会继续下架该用户仍在展示的所有广场投稿。`
      : `将禁止用户 ${targetName} 后续投稿，并下架该用户当前所有广场投稿。此操作不会删除文件或历史记录。`,
    okText: '封禁并下架',
    okType: 'danger',
    cancelText: '取消',
    onOk: async () => {
      try {
        const res = await banGalleryUserSubmissionsAndTakedown(record.user_id)
        message.success(`已封禁用户 ${record.user_id}，下架 ${res.affected_posts || 0} 条投稿`)
        await loadData()
      } catch (error) {
        message.error('操作失败: ' + (error.response?.data?.detail || error.message))
      }
    },
  })
}

const getMediaUrl = (url) => {
  if (!url) return ''
  if (url.startsWith('http')) return url
  return `${apiBaseUrl}${url}`
}

const showPreview = (record) => {
  if (!record.media_url) {
    message.warning('媒体文件不可用或已失效')
    return
  }
  previewMedia.value = {
    url: getMediaUrl(record.media_url),
    type: record.media_type
  }
  previewVisible.value = true
}

onMounted(() => {
  loadData()
})
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Header & Filters -->
    <div class="mb-4 flex flex-wrap gap-4 items-center justify-between">
      <div class="flex items-center gap-4">
        <h2 class="text-lg font-semibold m-0 flex items-center gap-2">
          <appstore-outlined class="text-blue-500" />
          广场内容管理
        </h2>
        
        <a-divider type="vertical" class="h-6" />
        
        <div class="flex items-center gap-2">
          <span class="text-gray-500">状态:</span>
          <a-select
            v-model:value="filterActive"
            :options="statusOptions"
            class="w-32"
            @change="onFilterChange"
          />
        </div>

        <div class="flex items-center gap-2">
          <span class="text-gray-500">类型:</span>
          <a-select
            v-model:value="filterTaskType"
            :options="taskTypeOptions"
            class="w-32"
            @change="onFilterChange"
          />
        </div>

        <div class="flex items-center gap-2">
          <span class="text-gray-500">排序:</span>
          <a-select
            v-model:value="filterSort"
            :options="sortOptions"
            class="w-32"
            @change="onFilterChange"
          />
        </div>
      </div>
      
      <a-button type="primary" @click="() => loadData(1)" :loading="loading">
        刷新数据
      </a-button>
    </div>

    <!-- Table -->
    <div class="flex-1 bg-white rounded-lg border overflow-hidden flex flex-col min-h-0">
      <a-table
        :columns="columns"
        :data-source="posts"
        :row-key="record => record.id"
        :pagination="pagination"
        :loading="loading"
        @change="handleTableChange"
        size="middle"
        :scroll="{ y: 'calc(100vh - 280px)', x: 'max-content' }"
        class="h-full"
      >
        <template #bodyCell="{ column, record }">
          <!-- Preview -->
          <template v-if="column.key === 'preview'">
            <div 
              class="w-24 h-24 rounded bg-gray-100 border cursor-pointer flex items-center justify-center hover:border-blue-400 transition-colors mx-auto relative group overflow-hidden"
              @click="showPreview(record)"
            >
              <template v-if="record.media_url">
                <img v-if="record.media_type === 'image'" :src="getMediaUrl(record.media_url)" class="w-full h-full object-cover" />
                <video v-else :src="getMediaUrl(record.media_url)" class="w-full h-full object-cover" />
                <div class="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
                  <play-circle-outlined v-if="record.media_type === 'video'" class="text-white text-3xl" />
                  <picture-outlined v-else class="text-white text-3xl" />
                </div>
              </template>
              <span v-else class="text-xs text-gray-400">失效</span>
            </div>
          </template>

          <!-- Author -->
          <template v-else-if="column.key === 'author'">
            <div class="min-w-[140px]">
              <div class="flex items-center gap-1.5 text-sm text-gray-700">
                <user-outlined class="text-gray-400 flex-shrink-0" />
                <span class="font-medium truncate" :title="getAuthorDisplayName(record)">
                  {{ getAuthorDisplayName(record) }}
                </span>
              </div>
              <div v-if="getAuthorMeta(record)" class="text-xs text-gray-400 mt-1">
                {{ getAuthorMeta(record) }}
              </div>
              <a-tag v-if="record.is_submission_banned" color="red" class="mt-1">
                投稿封禁
              </a-tag>
            </div>
          </template>

          <!-- Task Type -->
          <template v-else-if="column.key === 'task_type'">
            <a-tag :color="record.media_type === 'video' ? 'purple' : 'blue'">
              {{ getTaskTypeName(record.task_type) }}
            </a-tag>
          </template>

          <!-- Specs -->
          <template v-else-if="column.key === 'specs'">
            <div class="text-xs text-gray-500">
              <div>尺寸: {{ record.width || '?' }}x{{ record.height || '?' }}</div>
              <div v-if="record.media_type === 'video'">时长: {{ record.duration || '?' }}s</div>
            </div>
          </template>

          <!-- Prompt -->
          <template v-else-if="column.dataIndex === 'prompt'">
            <div class="flex items-start justify-between gap-2">
              <div class="text-sm text-gray-600 line-clamp-4 break-all whitespace-pre-wrap flex-1" :title="record.prompt">
                {{ record.prompt || '无' }}
              </div>
              <a-button 
                v-if="record.prompt" 
                type="text" 
                size="small" 
                class="text-gray-400 hover:text-blue-500 flex-shrink-0" 
                @click="copyToClipboard(record.prompt)"
                title="复制提示词"
              >
                <template #icon><copy-outlined /></template>
              </a-button>
            </div>
          </template>

          <!-- Stats -->
          <template v-else-if="column.key === 'stats'">
            <div class="flex flex-wrap gap-2">
              <a-tooltip title="点赞数">
                <a-tag color="success">👍 {{ record.likes_count }}</a-tag>
              </a-tooltip>
              <a-tooltip title="点踩数">
                <a-tag color="error">👎 {{ record.dislikes_count }}</a-tag>
              </a-tooltip>
              <a-tooltip title="应用次数">
                <a-tag color="processing">🪄 {{ record.applied_count }}</a-tag>
              </a-tooltip>
              <a-tooltip title="评论数">
                <a-tag color="purple">💬 {{ record.comments_count || 0 }}</a-tag>
              </a-tooltip>
            </div>
          </template>

          <!-- Status -->
          <template v-else-if="column.dataIndex === 'is_active'">
            <a-tag :color="record.is_active ? 'success' : 'default'" class="cursor-pointer" @click="toggleStatus(record)">
              <template #icon>
                <check-circle-outlined v-if="record.is_active" />
                <close-circle-outlined v-else />
              </template>
              {{ record.is_active ? '已展示' : '已下架' }}
            </a-tag>
          </template>

          <!-- Actions -->
          <template v-else-if="column.key === 'action'">
            <div class="flex flex-wrap gap-2 w-[300px]">
              <a-button size="small" @click="editPost(record)">修改数据</a-button>
              <a-button size="small" @click="openCommentsManager(record)">评论管理</a-button>
              <a-button size="small" danger @click="confirmBanAndTakedown(record)">
                <template #icon><stop-outlined /></template>
                {{ record.is_submission_banned ? '下架全部' : '封禁并下架' }}
              </a-button>
              <a-button size="small" danger @click="confirmDelete(record)">删除</a-button>
            </div>
          </template>
        </template>
      </a-table>
    </div>

    <!-- Edit Modal -->
    <a-modal
      v-model:open="editModalVisible"
      title="修改广场内容数据"
      @ok="handleEditSubmit"
      :confirmLoading="submitLoading"
      destroyOnClose
    >
      <a-form layout="vertical" v-if="editingPost">
        <a-form-item label="点赞数">
          <a-input-number v-model:value="editForm.likes_count" class="w-full" :min="0" />
        </a-form-item>
        <a-form-item label="点踩数">
          <a-input-number v-model:value="editForm.dislikes_count" class="w-full" :min="0" />
        </a-form-item>
        <a-form-item label="应用次数">
          <a-input-number v-model:value="editForm.applied_count" class="w-full" :min="0" />
        </a-form-item>
        <a-form-item label="评论数">
          <a-input-number v-model:value="editForm.comments_count" class="w-full" :min="0" />
        </a-form-item>
        <a-form-item label="标签 (JSON格式)">
          <a-textarea 
            v-model:value="editForm.tags" 
            :rows="4" 
            placeholder='例如: ["#风景", "#唯美"]'
          />
        </a-form-item>
        
        <a-alert message="提示词等核心参数不支持直接修改，以防用户应用时与原模板效果不符。" type="info" show-icon />
      </a-form>
    </a-modal>

    <!-- Preview Modal -->
    <a-modal
      v-model:open="previewVisible"
      title="媒体预览"
      :footer="null"
      width="600px"
      centered
      destroyOnClose
    >
      <div class="flex justify-center items-center bg-gray-100 rounded-lg p-2 min-h-[300px]">
        <img 
          v-if="previewMedia?.type === 'image'" 
          :src="previewMedia?.url" 
          class="max-w-full max-h-[60vh] object-contain rounded shadow-sm"
        />
        <video 
          v-else-if="previewMedia?.type === 'video'" 
          :src="previewMedia?.url" 
          controls 
          autoplay 
          loop 
          class="max-w-full max-h-[60vh] rounded shadow-sm"
        />
      </div>
    </a-modal>
  </div>
</template>
