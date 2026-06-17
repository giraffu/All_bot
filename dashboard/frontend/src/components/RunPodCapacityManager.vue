<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  CloudServerOutlined,
  DeleteOutlined,
  PlusOutlined,
  StopOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import {
  fetchRunPodOperations,
  fetchRunPodProfiles,
  scaleRunPodCapacity,
  terminateRunPodOperation,
} from '../api/api'

type RunPodProfile = {
  profile: string
  label: string
  supported_task_types: string[]
}

type ScaleRow = {
  profile: string
  count: number
}

type RunPodOperation = {
  id: string
  action: string
  profile: string
  requested_count?: number
  status: string
  created_at?: string
  started_at?: string
  ended_at?: string
  exit_code?: number
  error?: string
  can_terminate?: boolean
  terminate_requested?: boolean
  cleanup_status?: string
}

const emit = defineEmits<{
  changed: []
}>()

const fallbackProfiles: RunPodProfile[] = [
  {
    profile: 'img2img',
    label: 'img2img / img2img_lora',
    supported_task_types: ['img2img', 'img2img_lora'],
  },
  {
    profile: 'image_to_video',
    label: 'image_to_video',
    supported_task_types: ['image_to_video', 'video_insert', 'video_edit'],
  },
  {
    profile: 'wan22_video_v2',
    label: 'wan22_video_v2',
    supported_task_types: ['wan22_video_v2'],
  },
  {
    profile: 'i2i_pro',
    label: 'i2i_pro / txt2img / face_swap',
    supported_task_types: ['i2i_pro', 't2i-pornmaster-turbo', 'face_swap'],
  },
]

const open = ref(false)
const submitting = ref(false)
const terminatingOperationIds = ref<Set<string>>(new Set())
const profiles = ref<RunPodProfile[]>(fallbackProfiles)
const operations = ref<RunPodOperation[]>([])
const rows = ref<ScaleRow[]>([
  { profile: 'img2img', count: 1 },
])
const retryOptions = reactive({
  max_attempts: 100,
  retry_interval_seconds: 30,
})

let operationTimer: ReturnType<typeof setInterval> | null = null

const profileOptions = computed(() =>
  profiles.value.map(profile => ({
    value: profile.profile,
    label: profile.label,
  }))
)

const recentOperations = computed(() => operations.value.slice(0, 6))

const profileLabel = (profile: string) =>
  profiles.value.find(item => item.profile === profile)?.label || profile

const statusColor = (status: string) => {
  if (status === 'succeeded') return 'green'
  if (status === 'failed') return 'red'
  if (status === 'running') return 'blue'
  if (status === 'terminating') return 'orange'
  if (status === 'terminated') return 'orange'
  if (status === 'terminate_failed') return 'red'
  return 'default'
}

const canTerminateOperation = (operation: RunPodOperation) =>
  operation.can_terminate === true ||
  (operation.action === 'add' && operation.status === 'running' && !operation.terminate_requested)

const isTerminatingOperation = (operationId: string) =>
  terminatingOperationIds.value.has(operationId)

const setTerminatingOperation = (operationId: string, loading: boolean) => {
  const next = new Set(terminatingOperationIds.value)
  if (loading) {
    next.add(operationId)
  } else {
    next.delete(operationId)
  }
  terminatingOperationIds.value = next
}

const loadProfiles = async () => {
  try {
    const payload = await fetchRunPodProfiles()
    if (payload?.profiles?.length) {
      profiles.value = payload.profiles
    }
  } catch (err) {
    console.error(err)
  }
}

const loadOperations = async () => {
  try {
    const payload = await fetchRunPodOperations()
    operations.value = payload?.operations || []
  } catch (err) {
    console.error(err)
  }
}

const showModal = async () => {
  open.value = true
  await Promise.all([loadProfiles(), loadOperations()])
}

const addRow = () => {
  const selected = new Set(rows.value.map(row => row.profile))
  const nextProfile =
    profiles.value.find(profile => !selected.has(profile.profile))?.profile ||
    profiles.value[0]?.profile ||
    'img2img'
  rows.value = [
    ...rows.value,
    { profile: nextProfile, count: 1 },
  ]
}

const removeRow = (index: number) => {
  if (rows.value.length <= 1) return
  rows.value = rows.value.filter((_row, rowIndex) => rowIndex !== index)
}

const submit = async () => {
  const normalizedRows = rows.value.map(row => ({
    profile: row.profile,
    count: Number(row.count || 0),
  }))
  const duplicateProfiles = normalizedRows.filter(
    (row, index) => normalizedRows.findIndex(item => item.profile === row.profile) !== index
  )
  if (duplicateProfiles.length > 0) {
    message.warning('同一类型只保留一行新增数量')
    return
  }

  submitting.value = true
  try {
    const payload = await scaleRunPodCapacity({
      items: normalizedRows,
      retry_unavailable: true,
      max_attempts: retryOptions.max_attempts,
      retry_interval_seconds: retryOptions.retry_interval_seconds,
    })
    message.success(`已提交 ${payload?.operations?.length || normalizedRows.length} 个 RunPod 操作`)
    open.value = false
    await loadOperations()
    emit('changed')
  } catch (err) {
    console.error(err)
    message.error('RunPod 操作提交失败')
  } finally {
    submitting.value = false
  }
}

const terminateOperation = async (operation: RunPodOperation) => {
  setTerminatingOperation(operation.id, true)
  try {
    await terminateRunPodOperation(operation.id)
    message.success('已提交终止操作，正在释放对应 RunPod')
    await loadOperations()
    emit('changed')
  } catch (err) {
    console.error(err)
    message.error('RunPod 终止提交失败')
  } finally {
    setTerminatingOperation(operation.id, false)
  }
}

onMounted(() => {
  void loadOperations()
  operationTimer = setInterval(() => {
    void loadOperations()
  }, 10000)
})

onUnmounted(() => {
  if (operationTimer) {
    clearInterval(operationTimer)
    operationTimer = null
  }
})
</script>

<template>
  <a-button type="primary" ghost @click="showModal">
    <template #icon><cloud-server-outlined /></template>
    RunPod 管理
  </a-button>

  <a-modal
    v-model:open="open"
    title="RunPod 管理"
    :confirm-loading="submitting"
    ok-text="开始新增"
    cancel-text="取消"
    width="760px"
    @ok="submit"
  >
    <div class="flex flex-col gap-4">
      <div class="flex flex-col gap-2">
        <div
          v-for="(row, index) in rows"
          :key="`${row.profile}-${index}`"
          class="grid grid-cols-[1fr_120px_32px] gap-2 items-center"
        >
          <a-select
            v-model:value="row.profile"
            :options="profileOptions"
            size="middle"
          />
          <label class="runpod-row-count">
            <span>新增数量</span>
            <a-input-number
              v-model:value="row.count"
              :min="1"
              class="w-full"
            />
          </label>
          <a-button
            type="text"
            danger
            :disabled="rows.length <= 1"
            @click="removeRow(index)"
          >
            <template #icon><delete-outlined /></template>
          </a-button>
        </div>
        <a-button type="dashed" class="w-full" @click="addRow">
          <template #icon><plus-outlined /></template>
          添加类型
        </a-button>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label class="runpod-field">
          <span>库存轮询</span>
          <div class="flex gap-1">
            <a-input-number v-model:value="retryOptions.max_attempts" :min="1" :max="500" class="w-full" />
            <a-input-number v-model:value="retryOptions.retry_interval_seconds" :min="5" :max="3600" class="w-full" />
          </div>
        </label>
      </div>

      <div v-if="recentOperations.length" class="border-t border-gray-100 pt-3">
        <div class="text-xs font-bold text-gray-500 mb-2">最近操作</div>
        <div class="flex flex-col gap-2 max-h-48 overflow-y-auto pr-1 custom-scrollbar">
          <div
            v-for="operation in recentOperations"
            :key="operation.id"
            class="flex items-center justify-between gap-3 text-xs border border-gray-100 rounded px-2 py-1"
          >
            <span class="min-w-0 flex-1 truncate">
              {{ operation.action }} · {{ profileLabel(operation.profile) }}
              <span v-if="operation.requested_count !== null && operation.requested_count !== undefined">
                · 新增 {{ operation.requested_count }}
              </span>
            </span>
            <div class="flex items-center gap-2 shrink-0">
              <a-tag :color="statusColor(operation.status)" class="m-0 shrink-0">
                {{ operation.status }}
              </a-tag>
              <a-popconfirm
                v-if="canTerminateOperation(operation)"
                title="终止该次 RunPod 新增操作并释放对应 Pod？"
                ok-text="终止"
                cancel-text="取消"
                @confirm="terminateOperation(operation)"
              >
                <a-button
                  size="small"
                  danger
                  :loading="isTerminatingOperation(operation.id)"
                >
                  <template #icon><stop-outlined /></template>
                  终止
                </a-button>
              </a-popconfirm>
            </div>
          </div>
        </div>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.runpod-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #6b7280;
}

.runpod-row-count {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 11px;
  color: #6b7280;
}
</style>
