<script setup>
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'

import { fetchAllGalleryComments, updateGalleryComment } from '../api/api'
import { formatDate } from '../utils/helpers'

const props = defineProps({
  selectedPostId: {
    type: Number,
    default: undefined,
  },
})

const loading = ref(false)
const comments = ref([])
const actionLoading = ref({})
const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0,
})

const filterPostId = ref(undefined)
const filterStatus = ref('active')

const statusOptions = [
  { label: '显示中', value: 'active' },
  { label: '全部', value: 'all' },
  { label: '已删除', value: 'inactive' },
]

const columns = computed(() => [
  {
    title: '评论ID',
    dataIndex: 'id',
    width: 96,
  },
  {
    title: '所属帖子',
    key: 'post',
    width: 130,
  },
  {
    title: '作者',
    dataIndex: 'author_name',
    width: 140,
  },
  {
    title: '评论内容',
    dataIndex: 'content',
  },
  {
    title: '状态',
    dataIndex: 'is_active',
    width: 110,
  },
  {
    title: '发布时间',
    dataIndex: 'created_at',
    width: 180,
  },
  {
    title: '操作',
    key: 'action',
    width: 120,
    fixed: 'right',
  },
])

const buildParams = (page = pagination.value.current) => {
  const params = {
    page,
    page_size: pagination.value.pageSize,
  }

  if (typeof filterPostId.value === 'number' && filterPostId.value > 0) {
    params.post_id = filterPostId.value
  }

  if (filterStatus.value === 'active') {
    params.is_active = true
  } else if (filterStatus.value === 'inactive') {
    params.is_active = false
  }

  return params
}

const loadComments = async (page = pagination.value.current) => {
  try {
    loading.value = true
    const res = await fetchAllGalleryComments(buildParams(page))
    comments.value = res.items
    pagination.value = {
      ...pagination.value,
      current: res.page,
      pageSize: res.page_size,
      total: res.total,
    }
  } catch (error) {
    message.error(`加载评论失败: ${error.response?.data?.detail || error.message}`)
  } finally {
    loading.value = false
  }
}

const handleTableChange = (pag) => {
  pagination.value = {
    ...pagination.value,
    current: pag.current,
    pageSize: pag.pageSize,
  }
  loadComments(pag.current)
}

const applyFilters = () => {
  pagination.value = {
    ...pagination.value,
    current: 1,
  }
  loadComments(1)
}

const deleteComment = async (record) => {
  try {
    actionLoading.value[record.id] = true
    const response = await updateGalleryComment(record.id, { is_active: false })
    if (response.message === 'No change needed') {
      message.info('该评论已删除，正在刷新列表')
      await loadComments(pagination.value.current)
      return
    }
    message.success('评论已删除')
    if (record.is_active) {
      record.is_active = false
    }
    await loadComments(pagination.value.current)
  } catch (error) {
    message.error(`删除评论失败: ${error.response?.data?.detail || error.message}`)
  } finally {
    actionLoading.value[record.id] = false
  }
}

watch(
  () => props.selectedPostId,
  (postId) => {
    filterPostId.value = typeof postId === 'number' ? postId : undefined
    pagination.value = {
      ...pagination.value,
      current: 1,
    }
    void loadComments(1)
  },
  { immediate: true }
)
</script>

<template>
  <div class="h-full flex flex-col">
    <div class="mb-4 flex flex-wrap items-center justify-between gap-4">
      <div class="flex flex-wrap items-center gap-4">
        <h2 class="m-0 text-lg font-semibold">评论管理</h2>

        <div class="flex items-center gap-2">
          <span class="text-gray-500">帖子 ID:</span>
          <a-input-number
            v-model:value="filterPostId"
            :min="1"
            :precision="0"
            :controls="false"
            placeholder="全部"
            class="w-32"
          />
        </div>

        <div class="flex items-center gap-2">
          <span class="text-gray-500">状态:</span>
          <a-select
            v-model:value="filterStatus"
            :options="statusOptions"
            class="w-32"
          />
        </div>

        <a-button type="primary" @click="applyFilters">查询</a-button>
      </div>

      <a-button @click="loadComments(1)" :loading="loading">刷新数据</a-button>
    </div>

    <div class="flex-1 min-h-0 overflow-hidden rounded-lg border bg-white">
      <a-table
        :columns="columns"
        :data-source="comments"
        :row-key="record => record.id"
        :pagination="pagination"
        :loading="loading"
        :scroll="{ y: 'calc(100vh - 280px)', x: 980 }"
        size="middle"
        class="h-full"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'post'">
            <div class="text-sm leading-6">
              <div class="font-medium text-gray-900">#{{ record.post_id }}</div>
              <div class="text-xs text-gray-500">task: {{ record.post_task_id || '-' }}</div>
            </div>
          </template>

          <template v-else-if="column.dataIndex === 'content'">
            <div class="whitespace-pre-wrap break-words text-sm leading-6 text-gray-700">
              {{ record.content }}
            </div>
          </template>

          <template v-else-if="column.dataIndex === 'is_active'">
            <div class="flex flex-col gap-2">
              <a-tag :color="record.is_active ? 'success' : 'default'">
                {{ record.is_active ? '显示中' : '已删除' }}
              </a-tag>
              <a-tag :color="record.post_is_active ? 'blue' : 'default'">
                {{ record.post_is_active ? '帖子展示中' : '帖子已下架' }}
              </a-tag>
            </div>
          </template>

          <template v-else-if="column.dataIndex === 'created_at'">
            {{ formatDate(record.created_at) }}
          </template>

          <template v-else-if="column.key === 'action'">
            <a-popconfirm
              title="确认删除这条评论？"
              ok-text="删除"
              cancel-text="取消"
              @confirm="deleteComment(record)"
            >
              <a-button
                size="small"
                danger
                :disabled="!record.is_active"
                :loading="actionLoading[record.id]"
              >
                删除
              </a-button>
            </a-popconfirm>
          </template>
        </template>
      </a-table>
    </div>
  </div>
</template>
