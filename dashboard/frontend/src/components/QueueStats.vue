<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { 
  ThunderboltOutlined, 
  PictureOutlined, 
  VideoCameraOutlined,
  DashboardOutlined,
  SyncOutlined,
  RobotOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClearOutlined,
  HistoryOutlined,
  LockOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import {
  fetchRunPodAutoscaler,
  fetchRunPodOperations,
  updateRunPodAutoscalerSettings,
} from '../api/api'
import { useQueueStatsMonitor } from '../composables/useQueueStatsMonitor'
import LanAioFleetManager from './LanAioFleetManager.vue'
import RunPodCapacityManager from './RunPodCapacityManager.vue'
import RunPodWorkerActions from './RunPodWorkerActions.vue'
import WorkerHistoryModal from './WorkerHistoryModal.vue'

const {
  status,
  workers,
  concurrencyStats,
  cleaning,
  syncing,
  queueByTypeDisplay,
  runpodProfileQueueDisplay,
  cleanZombies,
  syncLock,
  updateQueue,
} = useQueueStatsMonitor()

const workerHistoryOpen = ref(false)
const selectedWorkerHistoryId = ref('')
const autoscalerConfig = ref({})
const autoscalerDecisions = ref([])
const thresholdDrafts = ref({})
const durationDrafts = ref({})
const savingSettingsProfile = ref('')
const togglingAutoscalerProfile = ref('')
const runpodOperationLogOpen = ref(false)
const runpodOperationLogLoading = ref(false)
const runpodOperations = ref([])
let autoscalerSettingsTimer = null
const autoscalerSettingsRefreshIntervalMs = 10000

const DEFAULT_SCALE_UP_WAIT_SECONDS_BY_PROFILE = {
  img2img: 20 * 60,
  image_to_video: 30 * 60,
  wan22_video_v2: 30 * 60,
  i2i_pro: 30 * 60,
  scail2: 40 * 60,
  ltx_video: 30 * 60,
}

const DEFAULT_TASK_DURATION_SECONDS_BY_TYPE = {
  img2img: 13,
  img2img_lora: 13,
  image_to_video: 60,
  wan22_video_v2: 60,
  i2i_pro: 12,
  't2i-pornmaster-turbo': 12,
  face_swap: 12,
  scail2_action_transfer: 300,
  scail2_video_replacement: 300,
  ltx_video: 120,
  ltx_video_flf2v: 120,
  ltx_video_v2v_audio: 120,
  unknown: 100,
}

const taskTotals = computed(() => {
  const totals = queueByTypeDisplay.value.reduce(
    (acc, item) => {
      acc.activeCount += Number(item.activeCount || 0)
      acc.pendingCount += Number(item.pendingCount || 0)
      return acc
    },
    { activeCount: 0, pendingCount: 0 }
  )

  if (queueByTypeDisplay.value.length === 0) {
    totals.activeCount = Number(status.value.queue_size || 0)
  }

  return totals
})

const RUNPOD_AGENT_ID_PATTERN =
  /^runpod_prod_(img2img|image_to_video|wan22_video_v2|i2i_pro|scail2|ltx_video)_manual_\d+$/

const splitWorkerTypes = (worker) =>
  String(worker.types || '')
    .split(',')
    .map((type) => type.trim())
    .filter(Boolean)

const isRunPodServerWorker = (worker) => {
  const provider = String(worker.provider || '').toLowerCase()
  const agentId = String(worker.agent_id || '')
  return provider === 'runpod' || RUNPOD_AGENT_ID_PATTERN.test(agentId)
}

const supportsRunPodProfile = (worker, profile) => {
  const supportedTaskTypes = new Set(profile.supportedTaskTypes || [])
  const runtimeProfile = String(worker.runtime_profile || '').trim()
  if (runtimeProfile && runtimeProfile === profile.profile) {
    return true
  }
  return splitWorkerTypes(worker).some((type) => supportedTaskTypes.has(type))
}

const runpodProfileRows = computed(() =>
  runpodProfileQueueDisplay.value.map((profile) => {
    const supportingWorkers = workers.value.filter((worker) =>
      supportsRunPodProfile(worker, profile)
    )
    const runpodServerCount = supportingWorkers.filter(isRunPodServerWorker).length
    return {
      ...profile,
      runpodServerCount,
      localWorkerCount: supportingWorkers.length - runpodServerCount,
    }
  })
)

const scaleUpThresholdSecondsByProfile = computed(() => ({
  ...DEFAULT_SCALE_UP_WAIT_SECONDS_BY_PROFILE,
  ...(autoscalerConfig.value?.scale_up_wait_seconds_by_profile || {}),
}))

const taskDurationSecondsByType = computed(() => ({
  ...DEFAULT_TASK_DURATION_SECONDS_BY_TYPE,
  ...(autoscalerConfig.value?.task_duration_seconds_by_type || {}),
}))

const profileAutoscalerPausedByProfile = computed(() => {
  const pausedProfiles = new Set(autoscalerConfig.value?.paused_profiles || [])
  return {
    ...(autoscalerConfig.value?.profile_autoscaler_paused_by_profile || {}),
    ...Array.from(pausedProfiles).reduce((acc, profile) => {
      acc[profile] = true
      return acc
    }, {}),
  }
})

const autoscalerDecisionsByProfile = computed(() =>
  autoscalerDecisions.value.reduce((acc, decision) => {
    if (decision?.profile) {
      acc[decision.profile] = decision
    }
    return acc
  }, {})
)

const thresholdMinutesForProfile = (profile) => {
  const seconds = Number(
    scaleUpThresholdSecondsByProfile.value[profile] ??
      DEFAULT_SCALE_UP_WAIT_SECONDS_BY_PROFILE[profile] ??
      30 * 60
  )
  return Math.max(1, Math.round(seconds / 60))
}

const thresholdDraftValue = (profile) => {
  const value = thresholdDrafts.value[profile]
  return value === undefined || value === null ? thresholdMinutesForProfile(profile) : value
}

const setThresholdDraft = (profile, value) => {
  thresholdDrafts.value = {
    ...thresholdDrafts.value,
    [profile]: value,
  }
}

const durationSecondsForProfile = (profileRow) => {
  const taskTypes = profileRow?.supportedTaskTypes || []
  const firstTaskType = taskTypes[0] || 'unknown'
  const seconds = Number(
    taskDurationSecondsByType.value[firstTaskType] ??
      DEFAULT_TASK_DURATION_SECONDS_BY_TYPE[firstTaskType] ??
      DEFAULT_TASK_DURATION_SECONDS_BY_TYPE.unknown
  )
  return Math.max(1, Math.round(seconds))
}

const durationDraftValue = (profileRow) => {
  const profile = profileRow.profile
  const value = durationDrafts.value[profile]
  return value === undefined || value === null ? durationSecondsForProfile(profileRow) : value
}

const setDurationDraft = (profile, value) => {
  durationDrafts.value = {
    ...durationDrafts.value,
    [profile]: value,
  }
}

const isThresholdValid = (profile) => {
  const minutes = Number(thresholdDraftValue(profile))
  return Number.isInteger(minutes) && minutes >= 1 && minutes <= 240
}

const isThresholdDirty = (profile) => {
  const minutes = Number(thresholdDraftValue(profile))
  return Number.isFinite(minutes) && minutes !== thresholdMinutesForProfile(profile)
}

const isDurationValid = (profileRow) => {
  const seconds = Number(durationDraftValue(profileRow))
  return Number.isInteger(seconds) && seconds >= 1 && seconds <= 3600
}

const isDurationDirty = (profileRow) => {
  const seconds = Number(durationDraftValue(profileRow))
  return Number.isFinite(seconds) && seconds !== durationSecondsForProfile(profileRow)
}

const isRunPodSettingsDirty = (profileRow) =>
  isThresholdDirty(profileRow.profile) || isDurationDirty(profileRow)

const syncThresholdDraftsFromConfig = () => {
  thresholdDrafts.value = runpodProfileQueueDisplay.value.reduce((acc, profile) => {
    acc[profile.profile] = thresholdMinutesForProfile(profile.profile)
    return acc
  }, {})
  durationDrafts.value = runpodProfileQueueDisplay.value.reduce((acc, profile) => {
    acc[profile.profile] = durationSecondsForProfile(profile)
    return acc
  }, {})
}

const loadAutoscalerSettings = async ({ syncDrafts = true } = {}) => {
  try {
    const payload = await fetchRunPodAutoscaler()
    autoscalerConfig.value = payload?.config || {}
    autoscalerDecisions.value = payload?.decisions || []
    if (syncDrafts) {
      syncThresholdDraftsFromConfig()
    }
  } catch (err) {
    console.error(err)
  }
}

const refreshAutoscalerDecisions = () => loadAutoscalerSettings({ syncDrafts: false })

const clearTimeDisplayForProfile = (profile) => {
  const decision = autoscalerDecisionsByProfile.value[profile]
  if (!decision) return '-'
  if (decision.capacity_status === 'no_accepting_workers') return '无可接单'
  return formatWaitDuration(decision.estimated_clear_time_seconds)
}

const decisionReasonForProfile = (profile) =>
  autoscalerDecisionsByProfile.value[profile]?.reason || ''

const isProfileAutoscalerPaused = (profile) =>
  profileAutoscalerPausedByProfile.value?.[profile] === true

const saveRunPodSettings = async (profileRow) => {
  const profile = profileRow.profile
  if (!isThresholdValid(profile)) {
    message.warning('清空阈值必须是 1-240 分钟')
    return
  }
  if (!isDurationValid(profileRow)) {
    message.warning('单任务耗时必须是 1-3600 秒')
    return
  }
  const minutes = Number(thresholdDraftValue(profile))
  const durationSeconds = Number(durationDraftValue(profileRow))
  const taskDurationUpdates = (profileRow.supportedTaskTypes || []).reduce((acc, taskType) => {
    acc[taskType] = durationSeconds
    return acc
  }, {})
  savingSettingsProfile.value = profile
  try {
    const payload = await updateRunPodAutoscalerSettings({
      scale_up_wait_minutes_by_profile: {
        [profile]: minutes,
      },
      task_duration_seconds_by_type: taskDurationUpdates,
      reason: 'dashboard clear-time settings update',
    })
    autoscalerConfig.value = payload?.config || autoscalerConfig.value
    autoscalerDecisions.value = payload?.decisions || autoscalerDecisions.value
    syncThresholdDraftsFromConfig()
    message.success(`已更新 ${profile} 清空阈值`)
  } catch (err) {
    console.error(err)
    message.error('清空阈值保存失败')
  } finally {
    savingSettingsProfile.value = ''
  }
}

const toggleProfileAutoscaler = async (profileRow) => {
  const profile = profileRow.profile
  const nextPaused = !isProfileAutoscalerPaused(profile)
  togglingAutoscalerProfile.value = profile
  try {
    const payload = await updateRunPodAutoscalerSettings({
      scale_up_wait_minutes_by_profile: {},
      task_duration_seconds_by_type: {},
      profile_autoscaler_paused_by_profile: {
        [profile]: nextPaused,
      },
      reason: nextPaused
        ? 'dashboard pause profile autoscaler'
        : 'dashboard resume profile autoscaler',
    })
    autoscalerConfig.value = payload?.config || autoscalerConfig.value
    autoscalerDecisions.value = payload?.decisions || autoscalerDecisions.value
    message.success(nextPaused ? `已暂停 ${profile} 自动管理` : `已恢复 ${profile} 自动管理`)
  } catch (err) {
    console.error(err)
    message.error('RunPod 类型自动管理状态更新失败')
  } finally {
    togglingAutoscalerProfile.value = ''
  }
}

const runpodCreateDeleteOperations = computed(() =>
  runpodOperations.value
    .filter((operation) => ['add', 'delete'].includes(String(operation.action || '')))
    .slice(0, 50)
)

const operationActionLabel = (action) => {
  if (action === 'add') return '创建'
  if (action === 'delete') return '删除'
  return action || '-'
}

const operationSourceLabel = (source) => {
  if (source === 'autoscaler') return '自动'
  return '手动'
}

const operationStatusColor = (status) => {
  if (status === 'succeeded') return 'green'
  if (status === 'failed') return 'red'
  if (status === 'running') return 'blue'
  if (status === 'terminated') return 'orange'
  if (status === 'terminating') return 'orange'
  if (status === 'terminate_failed') return 'red'
  return 'default'
}

const operationDetailText = (operation) => {
  if (operation.error) return operation.error
  if (operation.trigger_reason) return operation.trigger_reason
  const logTail = Array.isArray(operation.log_tail) ? operation.log_tail : []
  if (logTail.length > 0) return logTail[logTail.length - 1]
  return '-'
}

const formatOperationTime = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = (num) => String(num).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const loadRunPodOperationLogs = async () => {
  runpodOperationLogLoading.value = true
  try {
    const payload = await fetchRunPodOperations()
    runpodOperations.value = payload?.operations || []
  } catch (err) {
    console.error(err)
    message.error('RunPod 日志加载失败')
  } finally {
    runpodOperationLogLoading.value = false
  }
}

const openRunPodOperationLog = async () => {
  runpodOperationLogOpen.value = true
  await loadRunPodOperationLogs()
}

const handleCleanZombies = () => {
  Modal.confirm({
    title: '确认清理卡死任务？',
    content: '这将强制终止所有排队超过10分钟的任务，并自动为用户退款、释放并发锁。',
    okText: '确认清理',
    cancelText: '取消',
    okType: 'danger',
    onOk: async () => {
      try {
        const res = await cleanZombies()
        if (res.status === 'success') {
          message.success(`清理成功！共清除了 ${res.removed} 个卡死任务。`)
        } else {
          message.error('清理失败: ' + res.message)
        }
      } catch (err) {
        console.error(err)
        message.error('清理过程中发生错误')
      }
    }
  })
}

const formatDuration = (timestamp) => {
  if (!timestamp) return '-'
  const diff = Math.floor(Date.now() / 1000) - Math.floor(timestamp)
  if (diff < 0) return '0s'
  if (diff < 60) return `${diff}s`
  const m = Math.floor(diff / 60)
  const s = diff % 60
  return `${m}m ${s}s`
}

const formatWaitDuration = (seconds) => {
  if (seconds === null || seconds === undefined) return '-'
  const totalSeconds = Math.max(0, Math.floor(Number(seconds)))
  if (!Number.isFinite(totalSeconds)) return '-'
  if (totalSeconds < 60) return `${totalSeconds}s`
  const minutes = Math.floor(totalSeconds / 60)
  const remainingSeconds = totalSeconds % 60
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return `${hours}h ${remainingMinutes}m`
}

const formatTimeUntil = (timestamp) => {
  if (!timestamp) return '-'
  const diff = Math.ceil(Number(timestamp) - Date.now() / 1000)
  if (diff <= 0) return '即将恢复'
  if (diff < 60) return `${diff}s 后`
  const m = Math.floor(diff / 60)
  const s = diff % 60
  return `${m}m ${s}s 后`
}

const isPausedControlWorker = (worker) => {
  const controlState = String(worker.control_state || '').toLowerCase()
  return controlState === 'disabled' || controlState === 'draining'
}

const healthSummary = computed(() => {
  const activeWorkers = Number(status.value.active_workers || 0)
  const healthyWorkers = Number(status.value.healthy_workers || 0)
  const errorWorkers = Number(status.value.error_workers || 0)
  const quarantinedWorkers = Number(status.value.quarantined_workers || 0)
  const problemWorkers = errorWorkers + quarantinedWorkers

  if (activeWorkers <= 0) {
    return { color: 'error', text: '离线', online: false }
  }
  if (healthyWorkers <= 0) {
    return { color: 'error', text: '全部故障', online: false }
  }
  if (problemWorkers > 0) {
    return { color: 'warning', text: '部分故障', online: true }
  }
  return { color: 'success', text: '可用', online: true }
})

const getWorkerStatusMeta = (worker) => {
  if (isPausedControlWorker(worker)) {
    return {
      cardClass: 'border-t-2 border-t-orange-500',
      badgeStatus: 'warning',
      text: '暂停中',
      iconClass: 'text-orange-500',
      emptyText: '暂停接单中',
    }
  }
  if (worker.status === 'running') {
    return {
      cardClass: 'border-t-2 border-t-green-500',
      badgeStatus: 'processing',
      text: '忙碌',
      iconClass: 'text-green-500',
      emptyText: '任务执行中',
    }
  }
  if (worker.status === 'idle') {
    return {
      cardClass: 'border-t-2 border-t-gray-300',
      badgeStatus: 'default',
      text: '空闲',
      iconClass: 'text-gray-400',
      emptyText: '等待任务分发中...',
    }
  }
  if (worker.status === 'error') {
    return {
      cardClass: 'border-t-2 border-t-red-500',
      badgeStatus: 'error',
      text: '故障',
      iconClass: 'text-red-500',
      emptyText: 'ComfyUI 节点故障',
    }
  }
  if (worker.status === 'quarantined') {
    return {
      cardClass: 'border-t-2 border-t-orange-600',
      badgeStatus: 'warning',
      text: '已隔离',
      iconClass: 'text-orange-600',
      emptyText: '熔断隔离中',
    }
  }
  return {
    cardClass: 'border-t-2 border-t-gray-300',
    badgeStatus: 'default',
    text: '未知',
    iconClass: 'text-gray-400',
    emptyText: '状态未知',
  }
}

const isFaultWorker = (worker) =>
  !isPausedControlWorker(worker) && ['error', 'quarantined'].includes(worker.status)

const openWorkerHistory = (agentId) => {
  if (!agentId) return
  selectedWorkerHistoryId.value = agentId
  workerHistoryOpen.value = true
}

const handleWorkerHistoryOpenChange = (open) => {
  workerHistoryOpen.value = open
  if (!open) {
    selectedWorkerHistoryId.value = ''
  }
}

const handleSyncLock = async (userId) => {
  try {
    const res = await syncLock(userId)
    if (res.status === 'success') {
      message.success(res.message)
    } else {
      message.info(res.message)
    }
  } catch (err) {
    console.error(err)
    message.error('同步并发锁失败')
  }
}

onMounted(() => {
  void loadAutoscalerSettings()
  autoscalerSettingsTimer = setInterval(() => {
    void refreshAutoscalerDecisions()
  }, autoscalerSettingsRefreshIntervalMs)
})

onUnmounted(() => {
  if (autoscalerSettingsTimer) {
    clearInterval(autoscalerSettingsTimer)
    autoscalerSettingsTimer = null
  }
})
</script>

<template>
  <div class="mb-6">
    <div class="dashboard-monitor-toolbar flex items-center gap-2 mb-4">
      <dashboard-outlined class="text-blue-500 text-lg" />
      <h3 class="dashboard-monitor-title text-lg font-bold text-gray-800 m-0">系统实时监控</h3>
      <a-tag color="blue" class="ml-2 flex items-center gap-1">
        <template #icon><sync-outlined spin /></template>
        每秒自动刷新
      </a-tag>
      
      <div class="dashboard-monitor-actions ml-auto flex items-center gap-3">
        <run-pod-capacity-manager @changed="updateQueue" />
        <lan-aio-fleet-manager @changed="updateQueue" />
        <a-button type="primary" danger ghost @click="handleCleanZombies" :loading="cleaning">
          <template #icon><clear-outlined /></template>
          一键清理卡死任务
        </a-button>
        <a-tag :color="healthSummary.color">
          <template #icon>
            <check-circle-outlined v-if="healthSummary.online" />
            <close-circle-outlined v-else />
          </template>
          ComfyUI {{ healthSummary.text }}
        </a-tag>
      </div>
    </div>
    
    <a-row :gutter="[16, 16]" class="mb-4">
      <a-col :xs="24" :sm="8">
        <a-card hoverable class="queue-card border-l-4 border-l-blue-500 h-full">
          <div class="task-total-card" aria-label="任务总览">
            <div class="task-total-metric task-total-active">
              <div class="task-total-label">活跃数</div>
              <div class="task-total-value text-blue-500">
                <thunderbolt-outlined />
                <span>{{ taskTotals.activeCount }}</span>
              </div>
              <div class="task-total-caption">执行中或已占用</div>
            </div>
            <div class="task-total-divider" aria-hidden="true"></div>
            <div class="task-total-metric task-total-pending">
              <div class="task-total-label">排队数</div>
              <div class="task-total-value text-orange-500">
                <sync-outlined />
                <span>{{ taskTotals.pendingCount }}</span>
              </div>
              <div class="task-total-caption">等待 Worker 接单</div>
            </div>
          </div>
        </a-card>
      </a-col>
      
      <a-col :xs="24" :sm="8">
        <a-card hoverable class="queue-card border-l-4 border-l-green-500 h-full">
          <a-statistic
            title="活跃 Worker"
            :value="status.active_workers"
            :value-style="{ color: '#52c41a', fontWeight: 'bold' }"
          >
            <template #prefix>
              <robot-outlined />
            </template>
            <template #suffix>
              <span class="text-xs text-gray-400 font-normal ml-1">
                可接单 {{ status.healthy_workers || 0 }} / 故障 {{ (status.error_workers || 0) + (status.quarantined_workers || 0) }}
              </span>
            </template>
          </a-statistic>
        </a-card>
      </a-col>

      <a-col :xs="24" :sm="8">
        <a-card hoverable class="queue-card border-l-4 border-l-orange-500 h-full">
          <a-statistic
            title="用户并发锁"
            :value="status.concurrency_locks || 0"
            :value-style="{ color: '#fa8c16', fontWeight: 'bold' }"
          >
            <template #prefix>
              <lock-outlined />
            </template>
            <template #suffix>
              <span class="text-xs text-gray-400 font-normal ml-1">个活动锁</span>
            </template>
          </a-statistic>
        </a-card>
      </a-col>
    </a-row>

    <div class="queue-detail-grid mb-4">
      <a-card hoverable class="queue-card active-task-detail-card border-l-4 border-l-purple-500">
        <div class="flex items-center justify-between gap-3 mb-3">
          <div class="text-gray-700 font-bold">活跃任务详情</div>
          <a-tag color="purple" class="m-0">共 {{ queueByTypeDisplay.length }} 类</a-tag>
        </div>
        <div class="overflow-x-auto">
          <table class="active-task-detail-table">
            <colgroup>
              <col class="task-type-col" />
              <col class="task-metric-col" />
              <col class="task-metric-col" />
              <col class="task-wait-col" />
            </colgroup>
            <thead>
              <tr>
                <th>任务类型</th>
                <th>活跃数</th>
                <th>排队数</th>
                <th>最长排队等待</th>
              </tr>
            </thead>
            <tbody v-if="queueByTypeDisplay.length > 0">
              <tr v-for="item in queueByTypeDisplay" :key="item.type">
                <td>
                  <span class="task-type-cell" :title="item.type">{{ item.type }}</span>
                </td>
                <td>
                  <span class="metric-value text-purple-600">{{ item.activeCount }}</span>
                </td>
                <td>
                  <span class="metric-value text-blue-600">{{ item.pendingCount }}</span>
                </td>
                <td>
                  <span class="metric-value text-orange-600">
                    {{ formatWaitDuration(item.maxPendingWaitSeconds) }}
                  </span>
                </td>
              </tr>
            </tbody>
            <tbody v-else>
              <tr>
                <td colspan="4" class="empty-detail-cell">暂无活跃任务</td>
              </tr>
            </tbody>
          </table>
        </div>
      </a-card>

      <a-card hoverable class="queue-card runpod-profile-detail-card border-l-4 border-l-cyan-500">
        <div class="flex items-center justify-between gap-3 mb-3">
          <div class="text-gray-700 font-bold">活跃 RunPod 详情</div>
          <div class="runpod-detail-actions">
            <a-button
              size="small"
              class="runpod-log-button"
              :loading="runpodOperationLogLoading"
              @click="openRunPodOperationLog"
            >
              <template #icon><history-outlined /></template>
              日志
            </a-button>
            <a-tag color="cyan" class="m-0">共 {{ runpodProfileRows.length }} 类</a-tag>
          </div>
        </div>
        <div class="overflow-x-auto">
          <table class="runpod-profile-detail-table">
            <colgroup>
              <col class="runpod-profile-col" />
              <col class="runpod-server-col" />
              <col class="runpod-metric-col" />
              <col class="runpod-metric-col" />
              <col class="runpod-wait-col" />
              <col class="runpod-clear-time-col" />
              <col class="runpod-duration-col" />
              <col class="runpod-threshold-col" />
              <col class="runpod-autoscaler-col" />
            </colgroup>
            <thead>
              <tr>
                <th>RunPod 类型</th>
                <th>服务器</th>
                <th>活跃数</th>
                <th>排队数</th>
                <th>最长等待</th>
                <th>预计清空</th>
                <th>单任务耗时</th>
                <th>清空阈值</th>
                <th>自动管理</th>
              </tr>
            </thead>
            <tbody v-if="runpodProfileRows.length > 0">
              <tr v-for="item in runpodProfileRows" :key="item.profile">
                <td>
                  <div class="runpod-profile-cell">
                    <span class="runpod-profile-name" :title="item.profile">{{ item.profile }}</span>
                    <span
                      v-if="item.label && item.label !== item.profile"
                      class="runpod-profile-label"
                      :title="item.label"
                    >
                      {{ item.label }}
                    </span>
                    <span
                      class="runpod-task-types"
                      :title="item.supportedTaskTypes.join(', ')"
                    >
                      {{ item.supportedTaskTypes.join(' + ') }}
                    </span>
                  </div>
                </td>
                <td>
                  <div class="server-count-cell">
                    <span class="server-count-row">
                      <span class="server-count-label">RunPod</span>
                      <span class="server-count-value text-cyan-600">{{ item.runpodServerCount }}</span>
                    </span>
                    <span class="server-count-row">
                      <span class="server-count-label">本地</span>
                      <span class="server-count-value text-green-600">{{ item.localWorkerCount }}</span>
                    </span>
                  </div>
                </td>
                <td>
                  <span class="metric-value text-purple-600">{{ item.activeCount }}</span>
                </td>
                <td>
                  <span class="metric-value text-blue-600">{{ item.pendingCount }}</span>
                </td>
                <td>
                  <span class="metric-value text-orange-600">
                    {{ formatWaitDuration(item.maxPendingWaitSeconds) }}
                  </span>
                </td>
                <td>
                  <div class="clear-time-cell">
                    <span class="metric-value text-cyan-700">
                      {{ clearTimeDisplayForProfile(item.profile) }}
                    </span>
                    <span
                      v-if="decisionReasonForProfile(item.profile)"
                      class="runpod-decision-reason"
                      :title="decisionReasonForProfile(item.profile)"
                    >
                      {{ decisionReasonForProfile(item.profile) }}
                    </span>
                  </div>
                </td>
                <td>
                  <div class="task-duration-cell">
                    <a-input-number
                      size="small"
                      class="task-duration-input"
                      :min="1"
                      :max="3600"
                      :value="durationDraftValue(item)"
                      @update:value="value => setDurationDraft(item.profile, value)"
                    />
                    <span class="scale-threshold-unit">秒</span>
                  </div>
                </td>
                <td>
                  <div class="scale-threshold-cell">
                    <a-input-number
                      size="small"
                      class="scale-threshold-input"
                      :min="1"
                      :max="240"
                      :value="thresholdDraftValue(item.profile)"
                      @update:value="value => setThresholdDraft(item.profile, value)"
                    />
                    <span class="scale-threshold-unit">分钟</span>
                    <a-button
                      type="text"
                      size="small"
                      class="scale-threshold-save"
                      :disabled="!isRunPodSettingsDirty(item) || !isThresholdValid(item.profile) || !isDurationValid(item)"
                      :loading="savingSettingsProfile === item.profile"
                      @click="saveRunPodSettings(item)"
                    >
                      <template #icon><check-circle-outlined /></template>
                    </a-button>
                  </div>
                </td>
                <td>
                  <div class="profile-autoscaler-cell">
                    <a-tag
                      :color="isProfileAutoscalerPaused(item.profile) ? 'orange' : 'green'"
                      class="m-0"
                    >
                      {{ isProfileAutoscalerPaused(item.profile) ? '暂停中' : '自动' }}
                    </a-tag>
                    <a-button
                      type="text"
                      size="small"
                      class="profile-autoscaler-toggle"
                      :loading="togglingAutoscalerProfile === item.profile"
                      @click="toggleProfileAutoscaler(item)"
                    >
                      <template #icon>
                        <play-circle-outlined v-if="isProfileAutoscalerPaused(item.profile)" />
                        <pause-circle-outlined v-else />
                      </template>
                      {{ isProfileAutoscalerPaused(item.profile) ? '恢复' : '暂停' }}
                    </a-button>
                  </div>
                </td>
              </tr>
            </tbody>
            <tbody v-else>
              <tr>
                <td colspan="9" class="empty-detail-cell">暂无 RunPod 统计</td>
              </tr>
            </tbody>
          </table>
        </div>
      </a-card>
    </div>

    <a-modal
      v-model:open="runpodOperationLogOpen"
      title="RunPod 创建/删除日志"
      width="860px"
      :footer="null"
    >
      <div class="runpod-operation-log-panel">
        <div class="runpod-operation-log-toolbar">
          <span class="runpod-operation-log-count">
            最近 {{ runpodCreateDeleteOperations.length }} 条创建/删除记录
          </span>
          <a-button
            size="small"
            :loading="runpodOperationLogLoading"
            @click="loadRunPodOperationLogs"
          >
            <template #icon><sync-outlined /></template>
            刷新
          </a-button>
        </div>

        <div class="overflow-x-auto">
          <table
            v-if="runpodCreateDeleteOperations.length > 0"
            class="runpod-operation-log-table"
          >
            <thead>
              <tr>
                <th>时间</th>
                <th>操作</th>
                <th>类型</th>
                <th>来源</th>
                <th>状态</th>
                <th>Slot</th>
                <th>记录</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="operation in runpodCreateDeleteOperations"
                :key="operation.id"
              >
                <td class="operation-time-cell">
                  {{ formatOperationTime(operation.started_at || operation.created_at) }}
                </td>
                <td>
                  <span class="operation-action-cell">
                    {{ operationActionLabel(operation.action) }}
                    <span
                      v-if="operation.requested_count"
                      class="operation-count"
                    >
                      x{{ operation.requested_count }}
                    </span>
                  </span>
                </td>
                <td class="operation-profile-cell">{{ operation.profile || '-' }}</td>
                <td>{{ operationSourceLabel(operation.source) }}</td>
                <td>
                  <a-tag :color="operationStatusColor(operation.status)" class="m-0">
                    {{ operation.status || '-' }}
                  </a-tag>
                </td>
                <td class="operation-slot-cell">
                  {{ operation.slot || (operation.cleanup_slots || []).join(', ') || '-' }}
                </td>
                <td>
                  <span
                    class="operation-detail-cell"
                    :title="operationDetailText(operation)"
                  >
                    {{ operationDetailText(operation) }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="runpod-operation-log-empty">
            暂无 RunPod 创建/删除记录
          </div>
        </div>
      </div>
    </a-modal>

    <!-- Worker 实时状态卡片组 -->
    <div class="mb-2 mt-6">
      <h4 class="text-md font-bold text-gray-700 flex items-center gap-2">
        <robot-outlined class="text-green-500" /> Worker 节点实时状态
      </h4>
    </div>
    <a-row :gutter="[16, 16]">
      <a-col :xs="24" :sm="12" :md="8" :lg="6" v-for="worker in workers" :key="worker.agent_id">
        <a-card
          size="small"
          hoverable
          class="worker-card h-full flex flex-col"
          :class="getWorkerStatusMeta(worker).cardClass"
          role="button"
          tabindex="0"
          :aria-label="`查看 ${worker.agent_id} 的历史生成记录`"
          @click="openWorkerHistory(worker.agent_id)"
          @keydown.enter.prevent="openWorkerHistory(worker.agent_id)"
          @keydown.space.prevent="openWorkerHistory(worker.agent_id)"
        >
          <template #title>
            <div class="worker-card-title">
              <span class="worker-card-agent" :title="worker.agent_id">{{ worker.agent_id }}</span>
              <div class="worker-card-controls" @click.stop @keydown.stop>
                <run-pod-worker-actions :worker="worker" @changed="updateQueue" />
                <a-badge :status="getWorkerStatusMeta(worker).badgeStatus" :text="getWorkerStatusMeta(worker).text" />
              </div>
            </div>
          </template>
          
          <div class="flex flex-col gap-2 flex-grow">
            <!-- 正在执行的任务信息 -->
            <div v-if="worker.status === 'running' && worker.current_task_id" class="bg-gray-50 p-2 rounded text-sm flex-grow flex flex-col justify-between">
              <div>
                <div class="flex justify-between mb-1">
                  <span class="text-gray-500 text-xs">任务类型</span>
                  <a-tag color="purple" size="small" class="m-0 border-0">{{ worker.current_task_type || 'Unknown' }}</a-tag>
                </div>
                <div class="flex justify-between mb-2">
                  <span class="text-gray-500 text-xs">已执行</span>
                  <span class="font-mono text-xs text-gray-700">{{ formatDuration(worker.current_task_created_at) }}</span>
                </div>
                <div class="truncate text-xs text-gray-400 font-mono mb-2" :title="worker.current_task_id">
                  ID: {{ worker.current_task_id.substring(0, 8) }}...
                </div>
              </div>
              <div>
                <div class="flex justify-between text-xs mb-1">
                  <span class="text-gray-500">进度</span>
                  <span class="text-blue-600 font-bold">{{ Math.round((worker.current_task_progress || 0) * 100) }}%</span>
                </div>
                <a-progress :percent="Math.round((worker.current_task_progress || 0) * 100)" :show-info="false" size="small" strokeColor="#1890ff" class="m-0" />
              </div>
            </div>
            
            <!-- 空闲状态 -->
            <div v-else-if="isFaultWorker(worker)" class="flex-grow bg-red-50/70 border border-red-100 p-2 rounded text-sm">
              <div class="flex items-center gap-2 mb-2">
                <close-circle-outlined :class="getWorkerStatusMeta(worker).iconClass" />
                <span class="font-bold text-gray-700">{{ getWorkerStatusMeta(worker).emptyText }}</span>
              </div>
              <div class="text-xs text-gray-500 mb-1">原因</div>
              <div class="text-xs text-gray-700 break-words mb-2">{{ worker.last_error || worker.health_reason || '暂无错误详情' }}</div>
              <div class="grid grid-cols-2 gap-2 text-xs text-gray-500">
                <div>
                  <div>失败次数</div>
                  <span class="font-mono text-gray-700">{{ worker.consecutive_failures || 0 }}</span>
                </div>
                <div>
                  <div>{{ worker.status === 'quarantined' ? '预计恢复' : '故障时间' }}</div>
                  <span class="font-mono text-gray-700">
                    {{ worker.status === 'quarantined' ? formatTimeUntil(worker.quarantined_until) : formatDuration(worker.last_error_at) }}
                  </span>
                </div>
              </div>
            </div>

            <!-- 空闲或未知状态 -->
            <div v-else class="flex-grow flex flex-col items-center justify-center py-4 text-gray-400">
              <picture-outlined class="text-2xl mb-2 opacity-50" :class="getWorkerStatusMeta(worker).iconClass" />
              <span class="text-xs">{{ getWorkerStatusMeta(worker).emptyText }}</span>
            </div>
            
            <div class="mt-auto pt-2 border-t border-gray-100 text-xs text-gray-400 flex justify-between">
              <span class="truncate" :title="worker.types">支持: {{ worker.types.split(',').length }} 类</span>
              <span>心跳: {{ formatDuration(worker.last_seen) }} 前</span>
            </div>
          </div>
        </a-card>
      </a-col>
      <a-col :span="24" v-if="workers.length === 0">
        <a-empty description="暂无在线的 Worker 节点" />
      </a-col>
    </a-row>

    <!-- 用户并发锁与活跃任务表 -->
    <div class="mb-2 mt-6">
      <h4 class="text-md font-bold text-gray-700 flex items-center gap-2">
        <lock-outlined class="text-orange-500" /> 用户并发锁状态监控
      </h4>
    </div>
    <a-card class="mb-4">
      <a-table 
        :dataSource="concurrencyStats" 
        :rowKey="record => record.user_id" 
        size="small"
        :pagination="{ pageSize: 5 }"
      >
        <a-table-column title="用户 ID" dataIndex="user_id" key="user_id">
          <template #default="{ text }">
            <span class="font-mono text-gray-600">{{ text }}</span>
          </template>
        </a-table-column>
        <a-table-column title="用户名" dataIndex="username" key="username">
          <template #default="{ text }">
            <span class="font-bold text-gray-800">{{ text }}</span>
          </template>
        </a-table-column>
        <a-table-column title="当前并发锁" dataIndex="concurrency_locks" key="concurrency_locks">
          <template #default="{ text }">
            <a-tag :color="text > 0 ? 'orange' : 'default'">{{ text }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="活跃排队任务数" dataIndex="active_tasks" key="active_tasks">
          <template #default="{ text }">
            <a-tag :color="text > 0 ? 'blue' : 'default'">{{ text }}</a-tag>
          </template>
        </a-table-column>
        <a-table-column title="状态评估" key="status_eval">
          <template #default="{ record }">
            <a-tag v-if="record.concurrency_locks > record.active_tasks" color="red">可能有锁遗留</a-tag>
            <a-tag v-else-if="record.concurrency_locks === record.active_tasks && record.active_tasks > 0" color="green">正常执行</a-tag>
            <a-tag v-else-if="record.active_tasks > record.concurrency_locks" color="purple">超限排队</a-tag>
            <span v-else class="text-gray-400 text-xs">空闲</span>
          </template>
        </a-table-column>
        <a-table-column title="操作" key="action">
          <template #default="{ record }">
            <a-button 
              v-if="record.concurrency_locks > record.active_tasks" 
              type="primary" 
              size="small" 
              danger
              @click="handleSyncLock(record.user_id)"
              :loading="syncing[record.user_id]"
            >
              一键修复
            </a-button>
          </template>
        </a-table-column>
      </a-table>
    </a-card>

    <worker-history-modal
      :open="workerHistoryOpen"
      :worker-id="selectedWorkerHistoryId"
      @update:open="handleWorkerHistoryOpenChange"
    />
  </div>
</template>

<style scoped>
.queue-card {
  transition: all 0.3s;
  border-radius: 8px;
}
.queue-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.task-total-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 14px;
  min-height: 82px;
}
.task-total-metric {
  min-width: 0;
  text-align: center;
}
.task-total-label {
  color: #8c8c8c;
  font-size: 14px;
  line-height: 1.3;
  margin-bottom: 6px;
}
.task-total-value {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
}
.task-total-caption {
  color: #9ca3af;
  font-size: 12px;
  line-height: 1.3;
  margin-top: 5px;
  overflow-wrap: anywhere;
}
.task-total-divider {
  align-self: stretch;
  width: 1px;
  background: #eef0f3;
}
.worker-card {
  transition: all 0.3s;
  border-radius: 6px;
  cursor: pointer;
  outline: none;
}
.worker-card:focus-visible {
  box-shadow: 0 0 0 3px rgba(24, 144, 255, 0.22);
}
.worker-card :deep(.ant-card-head) {
  min-height: auto;
}
.worker-card :deep(.ant-card-head-title) {
  overflow: visible;
  white-space: normal;
  padding: 8px 0;
}
.worker-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
.worker-card-title {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  min-width: 0;
}
.worker-card-agent {
  display: block;
  color: #374151;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.3;
  overflow-wrap: anywhere;
  white-space: normal;
  word-break: break-word;
}
.worker-card-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  width: 100%;
}
.dashboard-monitor-toolbar {
  flex-wrap: wrap;
}
.dashboard-monitor-title {
  white-space: nowrap;
}
.dashboard-monitor-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}
.queue-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.active-task-detail-card,
.runpod-profile-detail-card {
  overflow: hidden;
  min-width: 0;
}
.runpod-detail-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.runpod-log-button {
  display: inline-flex;
  align-items: center;
}
.active-task-detail-table,
.runpod-profile-detail-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  font-size: 13px;
}
.active-task-detail-table {
  min-width: 520px;
}
.runpod-profile-detail-table {
  min-width: 1120px;
}
.task-type-col {
  width: 34%;
}
.task-metric-col {
  width: 20%;
}
.task-wait-col {
  width: 26%;
}
.runpod-profile-col {
  width: 24%;
}
.runpod-server-col {
  width: 12%;
}
.runpod-metric-col {
  width: 8%;
}
.runpod-wait-col {
  width: 11%;
}
.runpod-clear-time-col {
  width: 17%;
}
.runpod-duration-col {
  width: 13%;
}
.runpod-threshold-col {
  width: 15%;
}
.runpod-autoscaler-col {
  width: 13%;
}
.active-task-detail-table th,
.runpod-profile-detail-table th {
  color: #6b7280;
  font-weight: 600;
  text-align: left;
  background: #f9fafb;
  border-bottom: 1px solid #eef0f3;
  padding: 8px 12px;
}
.active-task-detail-table td,
.runpod-profile-detail-table td {
  border-bottom: 1px solid #f0f2f5;
  padding: 8px 12px;
  vertical-align: middle;
}
.active-task-detail-table tr:last-child td,
.runpod-profile-detail-table tr:last-child td {
  border-bottom: 0;
}
.task-type-cell {
  display: block;
  color: #374151;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  overflow-wrap: anywhere;
}
.runpod-profile-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}
.runpod-profile-name,
.runpod-task-types {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}
.runpod-profile-name {
  color: #374151;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.runpod-profile-label {
  color: #4b5563;
  font-size: 12px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}
.runpod-task-types {
  color: #6b7280;
  font-size: 11px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}
.server-count-cell {
  display: inline-flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.server-count-row {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}
.server-count-label {
  color: #6b7280;
  font-size: 11px;
  line-height: 1.2;
}
.server-count-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.2;
}
.metric-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-weight: 700;
}
.clear-time-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.runpod-decision-reason {
  display: block;
  color: #64748b;
  font-size: 10px;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-duration-cell {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}
.task-duration-input {
  width: 76px;
  flex: 0 0 76px;
}
.scale-threshold-cell {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}
.scale-threshold-input {
  width: 72px;
  flex: 0 0 72px;
}
.scale-threshold-unit {
  color: #6b7280;
  font-size: 11px;
  white-space: nowrap;
}
.scale-threshold-save {
  flex: 0 0 auto;
}
.profile-autoscaler-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  white-space: nowrap;
}
.profile-autoscaler-toggle {
  flex: 0 0 auto;
}
.runpod-operation-log-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.runpod-operation-log-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.runpod-operation-log-count {
  color: #64748b;
  font-size: 12px;
}
.runpod-operation-log-table {
  width: 100%;
  min-width: 780px;
  table-layout: fixed;
  border-collapse: collapse;
  font-size: 12px;
}
.runpod-operation-log-table th {
  color: #6b7280;
  font-weight: 600;
  text-align: left;
  background: #f9fafb;
  border-bottom: 1px solid #eef0f3;
  padding: 8px 10px;
}
.runpod-operation-log-table td {
  border-bottom: 1px solid #f0f2f5;
  padding: 8px 10px;
  vertical-align: middle;
}
.operation-time-cell,
.operation-profile-cell,
.operation-slot-cell {
  color: #475569;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}
.operation-action-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 700;
  color: #334155;
}
.operation-count {
  color: #64748b;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 11px;
  font-weight: 700;
}
.operation-detail-cell {
  display: block;
  color: #475569;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.runpod-operation-log-empty {
  padding: 28px 0;
  color: #9ca3af;
  text-align: center;
}
.empty-detail-cell {
  color: #9ca3af;
  text-align: center;
}
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #e5e7eb;
  border-radius: 4px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: #d1d5db;
}
@media (max-width: 1024px) {
  .dashboard-monitor-actions {
    justify-content: flex-start;
    margin-left: 0;
    width: 100%;
  }
  .queue-detail-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
