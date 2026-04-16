<script setup>
import { ref, onMounted, computed, h } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { ExclamationCircleOutlined, PictureOutlined, PlayCircleOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
import { fetchGalleryPosts, updateGalleryPost, deleteGalleryPost, apiBaseUrl } from '../api/api'
import { formatDate } from '../utils/helpers'

const loading = ref(false)
const posts = ref([])
const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0
})

// Filters
const filterActive = ref(undefined)
const filterType = ref('all')

const mediaTypeOptions = [
  { label: '全部', value: 'all' },
  { label: '图片', value: 'image' },
  { label: '视频', value: 'video' }
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
  tags: '[]'
})
const submitLoading = ref(false)

// Preview Modal
const previewVisible = ref(false)
const previewMedia = ref(null)

const columns = [
  {
    title: 'ID',
    dataIndex: 'id',
    width: 80,
  },
  {
    title: '作者',
    dataIndex: 'username',
    width: 120,
  },
  {
    title: '预览',
    key: 'preview',
    width: 80,
    align: 'center'
  },
  {
    title: '媒体类型',
    dataIndex: 'media_type',
    width: 100,
  },
  {
    title: '规格',
    key: 'specs',
    width: 120,
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
    title: '创建时间',
    dataIndex: 'created_at',
    width: 180,
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
    if (filterType.value !== 'all') {
      params.media_type = filterType.value
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
            v-model:value="filterType"
            :options="mediaTypeOptions"
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
          <!-- Username -->
          <template v-if="column.dataIndex === 'username'">
            <span class="font-medium">{{ record.username || `道友_${record.user_id}` }}</span>
          </template>

          <!-- Preview -->
          <template v-else-if="column.key === 'preview'">
            <div 
              class="w-12 h-12 rounded bg-gray-100 border cursor-pointer flex items-center justify-center hover:border-blue-400 transition-colors mx-auto relative group overflow-hidden"
              @click="showPreview(record)"
            >
              <template v-if="record.media_url">
                <img v-if="record.media_type === 'image'" :src="getMediaUrl(record.media_url)" class="w-full h-full object-cover" />
                <video v-else :src="getMediaUrl(record.media_url)" class="w-full h-full object-cover" />
                <div class="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
                  <play-circle-outlined v-if="record.media_type === 'video'" class="text-white text-lg" />
                  <picture-outlined v-else class="text-white text-lg" />
                </div>
              </template>
              <span v-else class="text-xs text-gray-400">失效</span>
            </div>
          </template>

          <!-- Media Type -->
          <template v-else-if="column.dataIndex === 'media_type'">
            <a-tag :color="record.media_type === 'video' ? 'purple' : 'blue'">
              {{ record.media_type === 'video' ? '视频' : '图片' }}
            </a-tag>
          </template>

          <!-- Specs -->
          <template v-else-if="column.key === 'specs'">
            <div class="text-xs text-gray-500">
              <div>尺寸: {{ record.width || '?' }}x{{ record.height || '?' }}</div>
              <div v-if="record.media_type === 'video'">时长: {{ record.duration || '?' }}s</div>
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

          <!-- Created At -->
          <template v-else-if="column.dataIndex === 'created_at'">
            {{ formatDate(record.created_at) }}
          </template>

          <!-- Actions -->
          <template v-else-if="column.key === 'action'">
            <div class="flex gap-2">
              <a-button size="small" @click="editPost(record)">修改数据</a-button>
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
