<script setup>
import { ref, onMounted, computed, h, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { ExclamationCircleOutlined, PictureOutlined, PlayCircleOutlined, CheckCircleOutlined, CloseCircleOutlined, CopyOutlined } from '@ant-design/icons-vue'
import { fetchGalleryPosts, updateGalleryPost, deleteGalleryPost, fetchGalleryComments, updateGalleryComment, apiBaseUrl } from '../api/api'
import { formatDate } from '../utils/helpers'

const loading = ref(false)
const posts = ref([])
const pagination = ref({
  current: 1,
  pageSize: 10,
  total: 0
})

const copyToClipboard = async (text) => {
  if (!text) return
  
  // 1. 尝试使用现代 Clipboard API (仅在 HTTPS 或 localhost 下可用)
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      message.success('提示词已复制')
      return
    } catch (err) {
      console.error('Clipboard API failed: ', err)
      // 如果失败，继续走下面的降级方案
    }
  }
  
  // 2. 降级方案：使用传统 execCommand，兼容 HTTP 环境 (如局域网 IP 访问)
  try {
    const textArea = document.createElement('textarea')
    textArea.value = text
    // 隐藏文本框，防止页面滚动闪烁
    textArea.style.position = 'fixed'
    textArea.style.left = '-999999px'
    textArea.style.top = '-999999px'
    
    document.body.appendChild(textArea)
    textArea.focus()
    textArea.select()
    
    const successful = document.execCommand('copy')
    document.body.removeChild(textArea)
    
    if (successful) {
      message.success('提示词已复制')
    } else {
      message.error('复制失败，浏览器可能拦截了该操作')
    }
  } catch (err) {
    message.error('复制失败')
    console.error('Fallback copy failed: ', err)
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

// Comments Manager Modal
const commentsModalVisible = ref(false)
const commentsPost = ref(null)
const comments = ref([])
const commentsLoading = ref(false)
const commentsActiveTotal = ref(0)
const commentsPagination = ref({
  current: 1,
  pageSize: 10,
  total: 0
})
const commentActionLoading = ref({})
let currentCommentsRequestId = 0

const invalidateCommentsRequests = () => {
  currentCommentsRequestId += 1
  commentsLoading.value = false
}

const getTaskTypeName = (type) => {
  const option = taskTypeOptions.find(opt => opt.value === type)
  return option ? option.label : type
}

const columns = [
  {
    title: '预览',
    key: 'preview',
    width: 120,
    align: 'center'
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
    width: 150,
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

const syncManagedPostCommentsCount = (count) => {
  if (!commentsPost.value) return
  commentsPost.value.comments_count = count
  const postInList = posts.value.find(post => post.id === commentsPost.value.id)
  if (postInList && postInList !== commentsPost.value) {
    postInList.comments_count = count
  }
}

const loadComments = async (page = commentsPagination.value.current) => {
  if (!commentsPost.value) return

  const postId = commentsPost.value.id
  const requestId = ++currentCommentsRequestId
  try {
    commentsLoading.value = true
    const res = await fetchGalleryComments({
      post_id: postId,
      page,
      page_size: commentsPagination.value.pageSize
    })
    if (
      requestId !== currentCommentsRequestId ||
      !commentsModalVisible.value ||
      commentsPost.value?.id !== postId
    ) {
      return
    }
    comments.value = res.items
    commentsActiveTotal.value = res.active_total ?? commentsPost.value?.comments_count ?? 0
    commentsPagination.value = {
      ...commentsPagination.value,
      current: res.page,
      pageSize: res.page_size,
      total: res.total
    }
  } catch (error) {
    message.error('加载评论失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    if (requestId === currentCommentsRequestId) {
      commentsLoading.value = false
    }
  }
}

const openCommentsManager = (record) => {
  invalidateCommentsRequests()
  commentsPost.value = record
  commentsActiveTotal.value = record.comments_count || 0
  commentsPagination.value = {
    ...commentsPagination.value,
    current: 1,
    total: 0
  }
  comments.value = []
  commentsModalVisible.value = true
  loadComments(1)
}

const handleCommentsPageChange = (page, pageSize) => {
  commentsPagination.value = {
    ...commentsPagination.value,
    current: page,
    pageSize
  }
  loadComments(page)
}

const toggleCommentStatus = async (comment) => {
  const nextStatus = !comment.is_active
  try {
    commentActionLoading.value[comment.id] = true
    const response = await updateGalleryComment(comment.id, { is_active: nextStatus })
    if (response.message === 'No change needed') {
      message.info('评论状态已被其他管理员更新，正在刷新')
      await loadComments(commentsPagination.value.current)
      return
    }

    comment.is_active = nextStatus

    if (commentsPost.value) {
      const nextCount = Math.max((commentsPost.value.comments_count || 0) + (nextStatus ? 1 : -1), 0)
      syncManagedPostCommentsCount(nextCount)
      commentsActiveTotal.value = nextCount
    }

    message.success(nextStatus ? '评论已恢复' : '评论已软删除')
  } catch (error) {
    message.error('更新评论失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    commentActionLoading.value[comment.id] = false
  }
}

watch(commentsModalVisible, (visible) => {
  if (!visible) {
    invalidateCommentsRequests()
    commentsPost.value = null
    comments.value = []
    commentsActiveTotal.value = 0
  }
})

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
            <div class="flex gap-2">
              <a-button size="small" @click="editPost(record)">修改数据</a-button>
              <a-button size="small" @click="openCommentsManager(record)">评论管理</a-button>
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

    <a-modal
      v-model:open="commentsModalVisible"
      :title="commentsPost ? `评论管理 - 帖子 #${commentsPost.id}` : '评论管理'"
      :footer="null"
      width="860px"
      destroyOnClose
    >
      <div class="space-y-4">
        <div v-if="commentsPost" class="flex items-center justify-between rounded border bg-gray-50 px-4 py-3">
          <div class="text-sm text-gray-600">
            显示中: <span class="font-semibold text-gray-900">{{ commentsActiveTotal }}</span>
            <span class="mx-2 text-gray-300">/</span>
            全部: <span class="font-semibold text-gray-900">{{ commentsPagination.total }}</span>
          </div>
          <a-button size="small" @click="loadComments(1)" :loading="commentsLoading">刷新评论</a-button>
        </div>

        <div v-if="commentsLoading && comments.length === 0" class="py-12 text-center text-gray-400">
          加载评论中...
        </div>

        <div v-else-if="comments.length === 0" class="py-12 text-center text-gray-400">
          暂无评论
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="comment in comments"
            :key="comment.id"
            class="rounded-lg border border-gray-200 bg-white p-4"
          >
            <div class="mb-2 flex items-center justify-between gap-3">
              <div class="flex items-center gap-3">
                <span class="font-medium text-gray-900">{{ comment.author_name }}</span>
                <a-tag :color="comment.is_active ? 'success' : 'default'">
                  {{ comment.is_active ? '显示中' : '已软删' }}
                </a-tag>
              </div>
              <div class="flex items-center gap-3">
                <span class="text-xs text-gray-400">{{ formatDate(comment.created_at) }}</span>
                <a-button
                  size="small"
                  :loading="commentActionLoading[comment.id]"
                  @click="toggleCommentStatus(comment)"
                >
                  {{ comment.is_active ? '软删除' : '恢复' }}
                </a-button>
              </div>
            </div>
            <div class="text-sm leading-6 text-gray-700 whitespace-pre-wrap break-words">{{ comment.content }}</div>
          </div>
        </div>

        <div class="flex justify-end">
          <a-pagination
            :current="commentsPagination.current"
            :page-size="commentsPagination.pageSize"
            :total="commentsPagination.total"
            :show-size-changer="false"
            @change="handleCommentsPageChange"
          />
        </div>
      </div>
    </a-modal>
  </div>
</template>
