<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import {
  CloudServerOutlined,
  DeleteOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  RobotOutlined,
  StopOutlined,
} from '@ant-design/icons-vue'
import message from 'ant-design-vue/es/message'
import {
  controlRunPodAutoscaler,
  fetchRunPodAutoscaler,
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
  source?: string
  trigger_reason?: string
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

type RunPodAutoscalerDecision = {
  profile: string
  action: string
  reason: string
  slot?: string | null
  pending_count?: number
  max_pending_wait_seconds?: number | null
  clear_time_threshold_seconds?: number
  estimated_clear_time_seconds?: number | null
  estimated_non_low_trust_clear_time_seconds?: number | null
  estimated_non_low_trust_pending_work_seconds?: number
  estimated_total_pending_work_seconds?: number
  non_low_trust_clear_pending_count?: number
  non_low_trust_clear_pending_count_by_task_type?: Record<string, number>
  last_non_low_trust_pending_queue_index?: number | null
  capacity_status?: string
  runpod_count?: number
  total_accepting_count?: number
}

type RunPodAutoscalerPayload = {
  enabled: boolean
  configured_enabled: boolean
  control_enabled: boolean
  mutation_skipped_reason?: string
  config?: {
    scale_up_wait_seconds?: number
    scale_down_wait_seconds?: number
    cooldown_seconds?: number
    max_runpods_per_profile?: number
    min_runpod_lifetime_seconds?: number
    runpod_fault_restart_seconds?: number
    runpod_bootstrap_timeout_seconds?: number
    runpod_bootstrap_replacement_limit?: number
    runpod_bootstrap_replacement_window_seconds?: number
    task_duration_seconds_by_type?: Record<string, number>
  }
  decisions?: RunPodAutoscalerDecision[]
  recent_operations?: RunPodOperation[]
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
    label: 'i2i_pro / txt2img / face_swap_v2',
    supported_task_types: ['i2i_pro', 't2i-pornmaster-turbo', 'face_swap_v2'],
  },
  {
    profile: 'scail2',
    label: 'scail2 / 视频生视频',
    supported_task_types: ['scail2_action_transfer', 'scail2_video_replacement'],
  },
  {
    profile: 'ltx_video',
    label: 'ltx_video / 高级图生视频',
    supported_task_types: ['ltx_video', 'ltx_video_flf2v', 'ltx_video_v2v_audio'],
  },
  {
    profile: 'pornmaster_flux2_edit',
    label: 'pornmaster_flux2 / 自由P图 v2',
    supported_task_types: [
      'pornmaster_flux2_single_edit',
      'pornmaster_flux2_multi_edit',
    ],
  },
  {
    profile: 'pornmaster_flux2_edit_bf16',
    label: 'pornmaster_flux2 BF16 / 自由P图 v2.5 + v3 共用执行池',
    supported_task_types: [
      'pornmaster_flux2_edit_bf16',
      'pornmaster_flux2_multi_edit_bf16',
    ],
  },
]

const open = ref(false)
const submitting = ref(false)
const autoscalerLoading = ref(false)
const autoscalerControlSubmitting = ref(false)
const terminatingOperationIds = ref<Set<string>>(new Set())
const profiles = ref<RunPodProfile[]>(fallbackProfiles)
const operations = ref<RunPodOperation[]>([])
const autoscaler = ref<RunPodAutoscalerPayload | null>(null)
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

const autoscalerDecisions = computed(() => autoscaler.value?.decisions || [])

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

const operationSourceLabel = (operation: RunPodOperation) =>
  operation.source === 'autoscaler' ? '自动' : '手动'

const operationSourceColor = (operation: RunPodOperation) =>
  operation.source === 'autoscaler' ? 'cyan' : 'default'

const operationActionLabel = (action: string) => {
  if (action === 'add') return '新增'
  if (action === 'delete') return '删除'
  if (action === 'restart') return '重启'
  if (action === 'enable') return '开启'
  if (action === 'pause') return '暂停'
  return action
}

const autoscalerDecisionLabel = (action: string) => {
  if (action === 'scale_up') return '扩容'
  if (action === 'scale_down') return '缩容'
  if (action === 'restart') return '重启'
  if (action === 'enable') return '开启'
  if (action === 'hold') return '保持'
  return action
}

const autoscalerDecisionColor = (action: string) => {
  if (action === 'scale_up') return 'blue'
  if (action === 'scale_down') return 'orange'
  if (action === 'restart') return 'red'
  if (action === 'enable') return 'green'
  return 'default'
}

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

const loadAutoscaler = async () => {
  autoscalerLoading.value = true
  try {
    autoscaler.value = await fetchRunPodAutoscaler()
  } catch (err) {
    console.error(err)
  } finally {
    autoscalerLoading.value = false
  }
}

const showModal = async () => {
  open.value = true
  await Promise.all([loadProfiles(), loadOperations(), loadAutoscaler()])
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

const setAutoscalerEnabled = async (enabled: boolean) => {
  autoscalerControlSubmitting.value = true
  try {
    autoscaler.value = await controlRunPodAutoscaler({
      enabled,
      reason: enabled ? 'dashboard resume' : 'dashboard pause',
    })
    message.success(enabled ? '已恢复 RunPod 自动管理' : '已暂停 RunPod 自动管理')
    await loadOperations()
  } catch (err) {
    console.error(err)
    message.error('RunPod 自动管理状态更新失败')
  } finally {
    autoscalerControlSubmitting.value = false
  }
}

onMounted(() => {
  void loadOperations()
  void loadAutoscaler()
  operationTimer = setInterval(() => {
    void loadOperations()
    void loadAutoscaler()
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
      <div class="runpod-autoscaler-panel">
        <div class="runpod-autoscaler-header">
          <div class="runpod-autoscaler-title">
            <robot-outlined />
            <span>自动管理</span>
            <a-tag :color="autoscaler?.enabled ? 'green' : 'default'" class="m-0">
              {{ autoscaler?.enabled ? '运行中' : '暂停' }}
            </a-tag>
          </div>
          <a-button
            size="small"
            :loading="autoscalerLoading || autoscalerControlSubmitting"
            @click="setAutoscalerEnabled(!autoscaler?.control_enabled)"
          >
            <template #icon>
              <pause-circle-outlined v-if="autoscaler?.control_enabled" />
              <play-circle-outlined v-else />
            </template>
            {{ autoscaler?.control_enabled ? '暂停自动管理' : '恢复自动管理' }}
          </a-button>
        </div>

        <div class="runpod-autoscaler-metrics">
          <span>清空阈值 {{ autoscaler?.config?.scale_up_wait_seconds || 1800 }}s</span>
          <span>缩容等待 {{ autoscaler?.config?.scale_down_wait_seconds || 60 }}s</span>
          <span>冷却 {{ autoscaler?.config?.cooldown_seconds || 600 }}s</span>
          <span>最短生命周期 {{ autoscaler?.config?.min_runpod_lifetime_seconds || 1800 }}s</span>
          <span>故障重启 {{ autoscaler?.config?.runpod_fault_restart_seconds || 300 }}s</span>
          <span>启动超时 {{ autoscaler?.config?.runpod_bootstrap_timeout_seconds || 2400 }}s</span>
          <span>替换上限 {{ autoscaler?.config?.runpod_bootstrap_replacement_limit || 2 }}</span>
          <span>每类最多 {{ autoscaler?.config?.max_runpods_per_profile || 5 }}</span>
        </div>

        <div
          v-if="autoscaler?.mutation_skipped_reason"
          class="runpod-autoscaler-warning"
        >
          {{ autoscaler.mutation_skipped_reason }}
        </div>

        <div v-if="autoscalerDecisions.length" class="runpod-autoscaler-decisions">
          <div
            v-for="decision in autoscalerDecisions"
            :key="decision.profile"
            class="runpod-autoscaler-decision"
          >
            <span class="runpod-autoscaler-profile">{{ profileLabel(decision.profile) }}</span>
            <a-tag :color="autoscalerDecisionColor(decision.action)" class="m-0">
              {{ autoscalerDecisionLabel(decision.action) }}
            </a-tag>
            <span class="runpod-autoscaler-reason" :title="decision.reason">
              {{ decision.reason }}
            </span>
          </div>
        </div>
      </div>

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
              {{ operationActionLabel(operation.action) }} · {{ profileLabel(operation.profile) }}
              <span v-if="operation.requested_count !== null && operation.requested_count !== undefined">
                · 新增 {{ operation.requested_count }}
              </span>
              <span v-if="operation.trigger_reason">
                · {{ operation.trigger_reason }}
              </span>
            </span>
            <div class="flex items-center gap-2 shrink-0">
              <a-tag :color="operationSourceColor(operation)" class="m-0 shrink-0">
                {{ operationSourceLabel(operation) }}
              </a-tag>
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

.runpod-autoscaler-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #d7f1f5;
  border-radius: 6px;
  background: #f7fdff;
}

.runpod-autoscaler-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.runpod-autoscaler-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-weight: 700;
  color: #334155;
}

.runpod-autoscaler-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  font-size: 11px;
  color: #64748b;
}

.runpod-autoscaler-warning {
  font-size: 12px;
  color: #b45309;
}

.runpod-autoscaler-decisions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.runpod-autoscaler-decision {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1.2fr);
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 12px;
}

.runpod-autoscaler-profile,
.runpod-autoscaler-reason {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 720px) {
  .runpod-autoscaler-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .runpod-autoscaler-metrics,
  .runpod-autoscaler-decisions {
    grid-template-columns: 1fr;
  }
}
</style>
