<template>
  <div class="h-full flex flex-col">
    <!-- Header Controls -->
    <div class="mb-4 flex justify-between items-center">
      <div class="flex items-center gap-4">
        <h2 class="text-xl font-semibold m-0">Worker 历史生成记录</h2>
        <a-select
          v-model:value="selectedWorker"
          style="width: 200px"
          placeholder="选择 Worker 节点"
          allowClear
          @change="handleWorkerChange"
        >
          <a-select-option value="">所有 Worker</a-select-option>
          <a-select-option v-for="worker in workerList" :key="worker" :value="worker">
            {{ worker }}
          </a-select-option>
        </a-select>
      </div>
      <a-button type="primary" @click="fetchHistory">
        <template #icon><sync-outlined /></template>
        刷新
      </a-button>
    </div>

    <!-- Data Table -->
    <div class="flex-1 overflow-hidden">
      <a-table
        :columns="columns"
        :data-source="historyData"
        :loading="loading"
        :pagination="pagination"
        @change="handleTableChange"
        row-key="id"
        size="middle"
        :scroll="{ y: 'calc(100vh - 280px)' }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <a-tag :color="record.status === 'success' ? 'success' : 'error'">
              {{ record.status === 'success' ? '成功' : '失败' }}
            </a-tag>
          </template>
          <template v-else-if="column.key === 'task_type'">
            <a-tag color="blue">{{ record.task_type }}</a-tag>
          </template>
          <template v-else-if="column.key === 'duration'">
            {{ record.duration }} 秒
          </template>
          <template v-else-if="column.key === 'start_time'">
            {{ formatDate(record.start_time) }}
          </template>
          <template v-else-if="column.key === 'error_message'">
            <div class="truncate max-w-[200px]" :title="record.error_message">
              {{ record.error_message || '-' }}
            </div>
          </template>
        </template>
      </a-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { SyncOutlined } from '@ant-design/icons-vue'
import dayjs from 'dayjs'
import {
  fetchWorkerHistory as fetchWorkerHistoryApi,
  fetchWorkerList as fetchWorkerListApi
} from '../api/api'

const loading = ref(false)
const historyData = ref([])
const workerList = ref([])
const selectedWorker = ref('')

const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0,
  showSizeChanger: true,
  showTotal: (total) => `共 ${total} 条记录`
})

const columns = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 80 },
  { title: 'Worker ID', dataIndex: 'worker_id', key: 'worker_id', width: 150 },
  { title: '任务ID', dataIndex: 'task_id', key: 'task_id', width: 250, ellipsis: true },
  { title: '任务类型', dataIndex: 'task_type', key: 'task_type', width: 120 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
  { title: '开始时间', dataIndex: 'start_time', key: 'start_time', width: 180 },
  { title: '耗时', dataIndex: 'duration', key: 'duration', width: 100 },
  { title: '错误信息', dataIndex: 'error_message', key: 'error_message', ellipsis: true }
]

const fetchWorkerList = async () => {
  try {
    const data = await fetchWorkerListApi()
    workerList.value = data.workers || []
  } catch (error) {
    console.error('Error fetching worker list:', error)
  }
}

const fetchHistory = async () => {
  loading.value = true
  try {
    const params = {
      page: pagination.value.current,
      size: pagination.value.pageSize
    }

    if (selectedWorker.value) {
      params.worker_id = selectedWorker.value
    }

    const data = await fetchWorkerHistoryApi({
      page: params.page,
      size: params.size,
      workerId: selectedWorker.value || null
    })

    historyData.value = data.data
    pagination.value.total = data.total
  } catch (error) {
    message.error('获取 Worker 历史记录失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

const handleTableChange = (pag) => {
  pagination.value.current = pag.current
  pagination.value.pageSize = pag.pageSize
  fetchHistory()
}

const handleWorkerChange = () => {
  pagination.value.current = 1
  fetchHistory()
}

const formatDate = (dateString) => {
  if (!dateString) return '-'
  return dayjs(dateString).format('YYYY-MM-DD HH:mm:ss')
}

onMounted(() => {
  fetchWorkerList()
  fetchHistory()
})
</script>
