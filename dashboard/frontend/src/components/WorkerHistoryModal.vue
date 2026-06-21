<template>
  <a-modal
    :open="open"
    width="1120px"
    :footer="null"
    destroy-on-close
    class="worker-history-modal"
    @cancel="closeModal"
  >
    <template #title>
      <div class="worker-history-title">
        <span>Worker 历史生成记录</span>
        <span v-if="workerId" class="worker-history-worker-id" :title="workerId">
          {{ workerId }}
        </span>
      </div>
    </template>

    <div class="worker-history-toolbar">
      <a-button type="primary" :loading="loading" @click="loadHistory">
        <template #icon><sync-outlined /></template>
        刷新
      </a-button>
    </div>

    <a-table
      :columns="columns"
      :data-source="historyData"
      :loading="loading"
      :pagination="paginationConfig"
      :scroll="{ x: 980, y: 520 }"
      row-key="id"
      size="small"
      @change="handleTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'status'">
          <a-tag :color="getStatusMeta(record.status).color">
            {{ getStatusMeta(record.status).text }}
          </a-tag>
        </template>
        <template v-else-if="column.key === 'task_type'">
          <a-tag color="blue">{{ record.task_type || '-' }}</a-tag>
        </template>
        <template v-else-if="column.key === 'duration'">
          {{ formatDuration(record.duration) }}
        </template>
        <template v-else-if="column.key === 'start_time'">
          {{ formatDate(record.start_time) }}
        </template>
        <template v-else-if="column.key === 'error_message'">
          <div class="worker-history-error" :title="record.error_message || '-'">
            {{ record.error_message || '-' }}
          </div>
        </template>
      </template>
    </a-table>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { SyncOutlined } from '@ant-design/icons-vue'
import dayjs from 'dayjs'
import { fetchWorkerHistory } from '../api/api'

interface WorkerHistoryRecord {
  id: number
  worker_id?: string | null
  task_id?: string | null
  task_type?: string | null
  status?: string | null
  start_time?: string | null
  end_time?: string | null
  duration?: number | null
  error_message?: string | null
}

const props = defineProps<{
  open: boolean
  workerId?: string | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const defaultPageSize = 10

const loading = ref(false)
const historyData = ref<WorkerHistoryRecord[]>([])
const pagination = reactive({
  current: 1,
  pageSize: defaultPageSize,
  total: 0,
})

let requestSeq = 0
let lastOpen = false
let lastWorkerId: string | null | undefined = null

const columns = [
  { title: 'ID', dataIndex: 'id', key: 'id', width: 80 },
  { title: 'Worker ID', dataIndex: 'worker_id', key: 'worker_id', width: 190, ellipsis: true },
  { title: '任务ID', dataIndex: 'task_id', key: 'task_id', width: 250, ellipsis: true },
  { title: '任务类型', dataIndex: 'task_type', key: 'task_type', width: 130 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 90 },
  { title: '开始时间', dataIndex: 'start_time', key: 'start_time', width: 170 },
  { title: '耗时', dataIndex: 'duration', key: 'duration', width: 90 },
  { title: '错误信息', dataIndex: 'error_message', key: 'error_message', ellipsis: true },
]

const paginationConfig = computed(() => ({
  current: pagination.current,
  pageSize: pagination.pageSize,
  total: pagination.total,
  showSizeChanger: true,
  pageSizeOptions: ['10', '20', '50'],
  showTotal: (total: number) => `共 ${total} 条记录`,
}))

const getStatusMeta = (status?: string | null) => {
  const normalized = String(status || '').toLowerCase()
  if (['success', 'succeeded', 'done'].includes(normalized)) {
    return { color: 'success', text: '成功' }
  }
  if (['failed', 'failure', 'error'].includes(normalized)) {
    return { color: 'error', text: '失败' }
  }
  return { color: 'default', text: status || '-' }
}

const formatDate = (dateString?: string | null) => {
  if (!dateString) return '-'
  return dayjs(dateString).format('YYYY-MM-DD HH:mm:ss')
}

const formatDuration = (duration?: number | null) => {
  if (duration === null || duration === undefined) return '-'
  return `${duration} 秒`
}

const loadHistory = async () => {
  if (!props.open || !props.workerId) {
    return
  }

  const seq = ++requestSeq
  loading.value = true
  try {
    const data = await fetchWorkerHistory({
      page: pagination.current,
      size: pagination.pageSize,
      workerId: props.workerId,
    })
    if (seq !== requestSeq) {
      return
    }
    historyData.value = data?.data || []
    pagination.total = Number(data?.total || 0)
  } catch (error) {
    if (seq !== requestSeq) {
      return
    }
    message.error('获取 Worker 历史记录失败')
    console.error(error)
  } finally {
    if (seq === requestSeq) {
      loading.value = false
    }
  }
}

const handleTableChange = (pag: { current?: number; pageSize?: number }) => {
  pagination.current = pag.current || 1
  pagination.pageSize = pag.pageSize || defaultPageSize
  void loadHistory()
}

const closeModal = () => {
  emit('update:open', false)
}

watch(
  () => [props.open, props.workerId] as const,
  ([open, workerId]) => {
    const openedNow = open && !lastOpen
    const workerChanged = workerId !== lastWorkerId
    lastOpen = open

    if (!open || !workerId) {
      requestSeq += 1
      loading.value = false
      if (!open) {
        lastWorkerId = null
      }
      return
    }

    if (openedNow || workerChanged) {
      pagination.current = 1
    }
    lastWorkerId = workerId
    void loadHistory()
  },
  { immediate: true },
)
</script>

<style scoped>
.worker-history-title {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.worker-history-worker-id {
  color: #6b7280;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
  white-space: normal;
}

.worker-history-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.worker-history-error {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
