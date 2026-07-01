<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, ref } from 'vue'
import {
  DownOutlined,
  ReloadOutlined,
  RightOutlined,
  RocketOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import {
  fetchLanAioProfiles,
  fetchLanAioSlots,
  fetchRunPodOperations,
  startLanAioSlotAction,
} from '../api/api'

type LanAioProfile = {
  profile: string
  runtime_profile?: string
  task_types?: string[]
  model_bundles?: string[]
  required_nodes?: string[]
  workflow?: string
  min_vram_gb?: number | null
  image_ref?: string | null
  all_in_one_image_ref?: string | null
  model_prefix?: string | null
  model_manifest_key?: string | null
}

type LanAioSlot = {
  id: string
  enabled?: boolean
  configured_current?: boolean
  runtime_current?: boolean
  current_source?: string
  phase?: string
  assignment_id?: string
  target_profile_id: string
  configured_profile_id?: string
  configured_task_types?: string[]
  live_runtime_profile?: string | null
  live_types?: string | null
  live_task_types?: string[]
  live_image_ref?: string | null
  runtime_drift?: boolean
  runtime_drift_reasons?: string[]
  live_state?: string
  switch_readiness?: 'ready' | 'warning' | 'blocked' | string
  switch_blockers?: string[]
  switch_blocker_labels?: string[]
  recover_readiness?: 'ready' | 'warning' | 'blocked' | string
  recover_blockers?: string[]
  recover_blocker_labels?: string[]
  recover_prefer?: 'old' | 'candidate' | string
  target_container_state?: {
    state?: string
    summary?: string
  }
  last_failed_operation_id?: string | null
  recovery_status?: string | null
  retargetable?: boolean
  replacement_targets?: LanAioReplacementTarget[]
  host_port?: number | null
  agent_id?: string
  container_name?: string
  ssh_host?: string
  node_id?: string
  comfy_id?: string
  gpu_index?: number | null
  legacy_worker_id?: string
  old_runtime_container?: string
  remote_dir?: string
  target_task_types?: string[]
  physical_slot_key?: string
  all_in_one_image_ref?: string | null
  model_prefix?: string | null
  model_manifest_key?: string | null
  min_vram_gb?: number | null
}

type LanAioReplacementTarget = {
  slot_id?: string
  physical_slot_key?: string
  node_id?: string
  gpu_index?: number | null
  host_port?: number | null
  live_runtime_profile?: string | null
  configured_profile_id?: string | null
  selectable?: boolean
  disabled_reason?: string | null
}

type LanAioWorker = {
  agent_id?: string
  status?: string
  current_task_id?: string | null
  current_task_type?: string | null
  runtime_profile?: string
  provider?: string
  pool_managed?: boolean | string | number
  image_ref?: string | null
}

type LanAioCache = {
  status?: string
  ok?: boolean
  profile?: string
  model_prefix?: string | null
  model_manifest_key?: string | null
  synced_at?: string
  error?: string
  raw?: string
}

type LanAioSlotStatus = {
  slot: LanAioSlot
  workers?: LanAioWorker[]
  control?: {
    legacy?: string
    aio?: string
  }
  remote_containers?: string[]
  model_cache?: LanAioCache
  live_state?: string
  switch_readiness?: string
  switch_blockers?: string[]
  recover_readiness?: string
  recover_blockers?: string[]
  target_container_state?: {
    state?: string
    summary?: string
  }
}

type LanAioSlotGroup = {
  physical_slot_key: string
  active_slot_id?: string | null
  active_slot_source?: string | null
  recoverable_slot_ids?: string[]
  recoverable_count?: number
  node_id?: string
  gpu_index?: number | null
  slots: LanAioSlotStatus[]
}

type LanAioNodeGroup = {
  node_key: string
  node_id: string
  gpu_labels: string[]
  slot_groups: LanAioSlotGroup[]
  slot_count: number
  current_count: number
  candidate_count: number
  recoverable_count: number
}

type RunPodOperation = {
  id: string
  action: string
  profile?: string
  slot?: string
  active_lan_aio_slot?: string | null
  status: string
  trigger_reason?: string
  created_at?: string
  started_at?: string
  ended_at?: string
  error?: string
}

type LanAioActionKey = 'takeover' | 'recover'

type LanAioAction = {
  key: LanAioActionKey
  label: string
  danger?: boolean
}

const emit = defineEmits<{
  changed: []
}>()

const slotActions: LanAioAction[] = [
  { key: 'takeover', label: '一键切换', danger: true },
  { key: 'recover', label: '恢复此 AIO' },
]

const open = ref(false)
const loading = ref(false)
const slotActionLoading = ref<Set<string>>(new Set())
const profiles = ref<LanAioProfile[]>([])
const groups = ref<LanAioSlotGroup[]>([])
const operations = ref<RunPodOperation[]>([])
const statusError = ref('')
const inspectionLoading = ref(false)
const lastInspectionAt = ref('')
const expandedNodeKeys = ref<Set<string>>(new Set())
const nodeExpansionInitialized = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | null = null

const profileById = computed(() => {
  const map = new Map<string, LanAioProfile>()
  profiles.value.forEach(profile => map.set(profile.profile, profile))
  return map
})

const lanAioOperations = computed(() =>
  operations.value
    .filter(operation => String(operation.action || '').startsWith('lan-aio-'))
    .slice(0, 8)
)

const activeLanAioOperationBySlot = computed(() => {
  const activeStatuses = new Set(['queued', 'pending', 'running', 'terminating'])
  return lanAioOperations.value.reduce((acc, operation) => {
    const key = operation.active_lan_aio_slot
    if (key && activeStatuses.has(String(operation.status || ''))) {
      acc.set(key, operation)
    }
    return acc
  }, new Map<string, RunPodOperation>())
})

const profileForSlot = (slot: LanAioSlot) =>
  profileById.value.get(slot.configured_profile_id || slot.target_profile_id)

const liveProfileForSlot = (slot: LanAioSlot) =>
  profileById.value.get(slot.live_runtime_profile || '')

const slotPhysicalKey = (slot: LanAioSlot) =>
  slot.physical_slot_key || `${slot.node_id || '-'}:gpu${slot.gpu_index ?? '-'}`

const slotActionLoadingKey = (slotId: string, action: string) => `${slotId}:${action}`

const isSlotActionLoading = (slotId: string, action: string) =>
  slotActionLoading.value.has(slotActionLoadingKey(slotId, action))

const setSlotActionLoading = (slotId: string, action: string, value: boolean) => {
  const next = new Set(slotActionLoading.value)
  const key = slotActionLoadingKey(slotId, action)
  if (value) {
    next.add(key)
  } else {
    next.delete(key)
  }
  slotActionLoading.value = next
}

const activeOperationForSlot = (slot: LanAioSlot) =>
  activeLanAioOperationBySlot.value.get(slotPhysicalKey(slot))

const isSlotLocked = (slot: LanAioSlot) => Boolean(activeOperationForSlot(slot))

const isCurrentSlot = (slotStatus: LanAioSlotStatus) =>
  slotStatus.slot.runtime_current ?? slotStatus.slot.enabled ?? false

const isInactiveRuntimeSlot = (slotStatus: LanAioSlotStatus) => {
  if (isCurrentSlot(slotStatus)) return false
  const phase = String(slotStatus.slot.phase || '')
  return (
    phase === 'maintenance_disabled' ||
    phase.startsWith('blocked_') ||
    (Boolean(slotStatus.slot.enabled) && !slotStatus.slot.live_runtime_profile)
  )
}

const slotStateLabel = (slotStatus: LanAioSlotStatus) => {
  if (isCurrentSlot(slotStatus)) return '当前'
  if (isInactiveRuntimeSlot(slotStatus)) return '停用'
  return '候选'
}

const slotStateColor = (slotStatus: LanAioSlotStatus) => {
  if (isCurrentSlot(slotStatus)) return 'green'
  if (isInactiveRuntimeSlot(slotStatus)) return 'default'
  return 'default'
}

const switchBlockerLabel = (reason: string) =>
  reason.replaceAll('_', ' ')

const switchBlockerLabels = (slot: LanAioSlot) =>
  slot.switch_blocker_labels?.length
    ? slot.switch_blocker_labels
    : (slot.switch_blockers || []).map(switchBlockerLabel)

const recoverBlockerLabels = (slot: LanAioSlot) =>
  slot.recover_blocker_labels?.length
    ? slot.recover_blocker_labels
    : (slot.recover_blockers || []).map(switchBlockerLabel)

const switchReadinessLabel = (slot: LanAioSlot) => {
  if (slot.switch_readiness === 'warning') return '需确认'
  if (slot.switch_readiness === 'blocked') return '阻断'
  if (slot.switch_readiness === 'ready') return '可切换'
  return ''
}

const switchReadinessColor = (slot: LanAioSlot) => {
  if (slot.switch_readiness === 'warning') return 'orange'
  if (slot.switch_readiness === 'blocked') return 'red'
  if (slot.switch_readiness === 'ready') return 'green'
  return 'default'
}

const allowsTakeoverAttempt = (slot: LanAioSlot) =>
  slot.switch_readiness === 'ready' || slot.switch_readiness === 'warning'

const recoverReadinessLabel = (slot: LanAioSlot) => {
  if (slot.recover_readiness === 'warning') return '可恢复'
  if (slot.recover_readiness === 'ready') return '可恢复'
  if (slot.recover_readiness === 'blocked') return '恢复阻断'
  return ''
}

const recoverReadinessColor = (slot: LanAioSlot) => {
  if (slot.recover_readiness === 'warning') return 'orange'
  if (slot.recover_readiness === 'ready') return 'green'
  if (slot.recover_readiness === 'blocked') return 'default'
  return 'default'
}

const liveStateLabel = (slot: LanAioSlot) => {
  if (slot.live_state === 'running') return '运行态'
  if (slot.live_state === 'stopped') return '已停止'
  if (slot.live_state === 'missing') return '无运行态'
  if (slot.live_state === 'unknown') return '运行态未知'
  return ''
}

const isSlotActionDisabled = (slotStatus: LanAioSlotStatus, action: LanAioAction) =>
  isSlotLocked(slotStatus.slot) ||
  (action.key === 'takeover' && slotStatus.slot.switch_readiness === 'blocked') ||
  (action.key === 'takeover' &&
    isInactiveRuntimeSlot(slotStatus) &&
    !allowsTakeoverAttempt(slotStatus.slot)) ||
  (action.key === 'takeover' && isCurrentSlot(slotStatus)) ||
  (action.key === 'takeover' &&
    Boolean(slotStatus.slot.retargetable) &&
    selectableReplacementTargets(slotStatus.slot).length === 0) ||
  (action.key === 'recover' && isCurrentSlot(slotStatus)) ||
  (action.key === 'recover' && slotStatus.slot.recover_readiness === 'blocked') ||
  (action.key === 'recover' && !slotStatus.slot.recover_readiness)

const actionDisabledReason = (slotStatus: LanAioSlotStatus, action: LanAioAction) => {
  if (isSlotLocked(slotStatus.slot)) return '同一物理 GPU 已有操作运行中'
  if (action.key === 'recover' && isCurrentSlot(slotStatus)) return '当前运行 slot 不需要恢复'
  if (action.key === 'recover' && slotStatus.slot.recover_readiness === 'blocked') {
    return recoverBlockerLabels(slotStatus.slot).join(' / ') || '恢复巡检阻断'
  }
  if (action.key === 'recover' && !slotStatus.slot.recover_readiness) {
    return '先巡检本地服务'
  }
  if (action.key === 'takeover' && slotStatus.slot.switch_readiness === 'blocked') {
    return switchBlockerLabels(slotStatus.slot).join(' / ') || '切换预检阻断'
  }
  if (
    action.key === 'takeover' &&
    isInactiveRuntimeSlot(slotStatus) &&
    !allowsTakeoverAttempt(slotStatus.slot)
  ) {
    return 'maintenance disabled / 无本地 GPU live runtime'
  }
  if (action.key === 'takeover' && isCurrentSlot(slotStatus)) return '当前运行 slot 不需要切换'
  if (
    action.key === 'takeover' &&
    slotStatus.slot.retargetable &&
    selectableReplacementTargets(slotStatus.slot).length === 0
  ) {
    return '没有可替换的同服务器当前服务'
  }
  return action.label
}

const nodeKeyForGroup = (group: LanAioSlotGroup) =>
  group.node_id ||
  group.slots[0]?.slot.node_id ||
  group.physical_slot_key.split(':')[0] ||
  'unknown-node'

const slotGroupGpuLabel = (group: LanAioSlotGroup) => {
  const gpuIndex = group.gpu_index ?? group.slots[0]?.slot.gpu_index
  if (gpuIndex !== null && gpuIndex !== undefined) {
    return `gpu${gpuIndex}`
  }
  return group.physical_slot_key
}

const nodeGroups = computed<LanAioNodeGroup[]>(() => {
  const map = new Map<string, LanAioNodeGroup>()

  groups.value.forEach(group => {
    const key = nodeKeyForGroup(group)
    let nodeGroup = map.get(key)
    if (!nodeGroup) {
      nodeGroup = {
        node_key: key,
        node_id: key,
        gpu_labels: [],
        slot_groups: [],
        slot_count: 0,
        current_count: 0,
        candidate_count: 0,
        recoverable_count: 0,
      }
      map.set(key, nodeGroup)
    }

    nodeGroup.slot_groups.push(group)
    const gpuLabel = slotGroupGpuLabel(group)
    if (!nodeGroup.gpu_labels.includes(gpuLabel)) {
      nodeGroup.gpu_labels.push(gpuLabel)
    }

    group.slots.forEach(slotStatus => {
      nodeGroup.slot_count += 1
      if (isCurrentSlot(slotStatus)) {
        nodeGroup.current_count += 1
      } else {
        nodeGroup.candidate_count += 1
      }
      if (slotStatus.slot.recover_readiness === 'ready' || slotStatus.slot.recover_readiness === 'warning') {
        nodeGroup.recoverable_count += 1
      }
    })
  })

  return Array.from(map.values())
})

const totalRecoverableCount = computed(() =>
  nodeGroups.value.reduce(
    (total, nodeGroup) => total + nodeGroup.recoverable_count,
    0
  )
)

const syncExpandedNodes = () => {
  const keys = nodeGroups.value.map(nodeGroup => nodeGroup.node_key)
  const allowedKeys = new Set(keys)
  const next = new Set(
    Array.from(expandedNodeKeys.value).filter(key => allowedKeys.has(key))
  )

  if (!nodeExpansionInitialized.value && keys.length > 0) {
    next.add(keys[0])
    nodeExpansionInitialized.value = true
  }

  expandedNodeKeys.value = next
}

const isNodeExpanded = (nodeKey: string) => expandedNodeKeys.value.has(nodeKey)

const toggleNode = (nodeKey: string) => {
  const next = new Set(expandedNodeKeys.value)
  if (next.has(nodeKey)) {
    next.delete(nodeKey)
  } else {
    next.add(nodeKey)
  }
  expandedNodeKeys.value = next
}

const expandAllNodes = () => {
  expandedNodeKeys.value = new Set(nodeGroups.value.map(nodeGroup => nodeGroup.node_key))
}

const collapseAllNodes = () => {
  expandedNodeKeys.value = new Set()
}

const activeOperationForGroup = (group: LanAioSlotGroup) => {
  for (const slotStatus of group.slots) {
    const operation = activeOperationForSlot(slotStatus.slot)
    if (operation) return operation
  }
  return undefined
}

const activeOperationsForNode = (nodeGroup: LanAioNodeGroup) => {
  const seen = new Set<string>()
  const activeOperations: RunPodOperation[] = []

  nodeGroup.slot_groups.forEach(group => {
    group.slots.forEach(slotStatus => {
      const operation = activeOperationForSlot(slotStatus.slot)
      if (operation && !seen.has(operation.id)) {
        seen.add(operation.id)
        activeOperations.push(operation)
      }
    })
  })

  return activeOperations
}

const loadProfiles = async () => {
  try {
    const payload = await fetchLanAioProfiles()
    profiles.value = payload?.profiles || []
  } catch (err) {
    console.error(err)
  }
}

const loadSlots = async () => {
  try {
    const payload = await fetchLanAioSlots(true)
    groups.value = payload?.groups || []
    statusError.value = payload?.status_error || ''
    syncExpandedNodes()
  } catch (err) {
    console.error(err)
    statusError.value = 'LAN AIO slot 状态加载失败'
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

const refresh = async () => {
  loading.value = true
  try {
    await Promise.all([loadProfiles(), loadSlots(), loadOperations()])
  } finally {
    loading.value = false
  }
}

const inspectLocalServers = async () => {
  inspectionLoading.value = true
  try {
    await refresh()
    lastInspectionAt.value = formatOperationTime(new Date().toISOString())
    message.success('本地服务器巡检完成')
  } finally {
    inspectionLoading.value = false
  }
}

const showModal = async () => {
  open.value = true
  await refresh()
}

const actionLabel = (action: string) =>
  slotActions.find(item => item.key === action)?.label || action

const submitSlotAction = async (
  slot: LanAioSlot,
  action: LanAioActionKey,
  replacementTargetSlotId?: string
) => {
  setSlotActionLoading(slot.id, action, true)
  try {
    await startLanAioSlotAction(slot.id, action, {
      failure_policy: 'auto_rollback',
      reason: `dashboard lan aio ${action}`,
      ...(replacementTargetSlotId
        ? { replacement_target_slot_id: replacementTargetSlotId }
        : {}),
    })
    message.success(`已提交 ${actionLabel(action)} 操作`)
    await Promise.all([loadSlots(), loadOperations()])
    emit('changed')
  } catch (err) {
    console.error(err)
    message.error(`${actionLabel(action)} 提交失败`)
  } finally {
    setSlotActionLoading(slot.id, action, false)
  }
}

const preferredReplacementTarget = (slot: LanAioSlot) => {
  const targets = selectableReplacementTargets(slot)
  return targets.find(target =>
    target.physical_slot_key && target.physical_slot_key === slotPhysicalKey(slot)
  ) || targets[0]
}

const confirmSlotAction = (slotStatus: LanAioSlotStatus, action: LanAioAction) => {
  const slot = slotStatus.slot
  const selectableTargets = selectableReplacementTargets(slot)
  let selectedTargetSlotId = preferredReplacementTarget(slot)?.slot_id || ''
  const replacementTargetOptions = slot.replacement_targets || []
  const blockerLabels = switchBlockerLabels(slot)
  const recoverLabels = recoverBlockerLabels(slot)
  if (action.key === 'recover') {
    const content = h('div', { class: 'takeover-confirm' }, [
      h('div', { class: 'takeover-summary' }, [
        `恢复 ${displayProfileId(slot)} 到 ${slotPhysicalKey(slot)}`,
      ]),
      h('div', { class: 'takeover-policy' }, '恢复策略：禁用同卡其它 AIO，启动/重建目标容器并验证 heartbeat 后启用接单'),
      ...(recoverLabels.length
        ? [
            h('div', { class: 'takeover-blockers' }, [
              h('span', '巡检提示：'),
              h('span', recoverLabels.join(' / ')),
            ]),
          ]
        : []),
    ])
    Modal.confirm({
      title: `${action.label}：${slot.id}`,
      content,
      zIndex: 1800,
      centered: true,
      width: 480,
      getContainer: () => document.body,
      okText: action.label,
      cancelText: '取消',
      onOk: () => submitSlotAction(slot, action.key),
    })
    return
  }
  if (slot.retargetable && action.key === 'takeover' && !selectedTargetSlotId) {
    message.error('没有可替换的同服务器当前服务')
    return
  }
  const takeoverContentChildren = [
    h('div', { class: 'takeover-summary' }, [
      `候选 ${displayProfileId(slot)} 将替换同服务器当前服务`,
    ]),
    h('div', { class: 'takeover-policy' }, '失败策略：自动回滚旧服务'),
  ]
  if (blockerLabels.length) {
    takeoverContentChildren.push(
      h('div', { class: 'takeover-blockers' }, [
        h('span', '切换提示：'),
        h('span', blockerLabels.join(' / ')),
      ])
    )
  }
  takeoverContentChildren.push(
    h('select', {
      class: 'takeover-target-select',
      value: selectedTargetSlotId,
      onChange: (event: Event) => {
        selectedTargetSlotId = String((event.target as HTMLSelectElement).value || '')
      },
    }, replacementTargetOptions.map(target =>
      h('option', {
        value: target.slot_id,
        disabled: !target.selectable,
      }, replacementTargetLabel(target))
    ))
  )
  const content = slot.retargetable && action.key === 'takeover'
    ? h('div', { class: 'takeover-confirm' }, takeoverContentChildren)
    : `${slotPhysicalKey(slot)} / ${displayProfileId(slot)}`
  Modal.confirm({
    title: `${action.label}：${slot.id}`,
    content,
    zIndex: 1800,
    centered: true,
    width: 480,
    getContainer: () => document.body,
    okText: action.label,
    okType: action.danger ? 'danger' : 'primary',
    cancelText: '取消',
    onOk: () => submitSlotAction(slot, action.key, selectedTargetSlotId || undefined),
  })
}

const cacheStatusColor = (cache?: LanAioCache) => {
  const status = cache?.status || (cache?.ok ? 'ready' : 'unknown')
  if (status === 'ready') return 'green'
  if (status === 'missing') return 'default'
  if (['invalid', 'unavailable', 'failed'].includes(status)) return 'red'
  return 'blue'
}

const controlStateColor = (state?: string) => {
  if (state === 'enabled') return 'green'
  if (state === 'disabled' || state === 'draining') return 'orange'
  if (state?.startsWith('unknown')) return 'default'
  return 'blue'
}

const workerStatusColor = (status?: string) => {
  if (status === 'idle') return 'green'
  if (status === 'running') return 'blue'
  if (status === 'error' || status === 'quarantined') return 'red'
  return 'default'
}

const operationStatusColor = (status?: string) => {
  if (status === 'succeeded') return 'green'
  if (status === 'failed') return 'red'
  if (status === 'running') return 'blue'
  if (status === 'terminated' || status === 'terminating') return 'orange'
  return 'default'
}

const cacheStatusLabel = (cache?: LanAioCache) =>
  cache?.status || (cache?.ok ? 'ready' : 'unknown')

const cacheDetail = (cache?: LanAioCache) => {
  if (!cache) return '-'
  if (cache.synced_at) return cache.synced_at
  if (cache.error) return cache.error
  if (cache.raw) return cache.raw
  return cache.model_manifest_key || cache.model_prefix || '-'
}

const profileTaskTypes = (slot: LanAioSlot) => {
  if (slot.live_task_types?.length) return slot.live_task_types
  if (slot.configured_task_types?.length) return slot.configured_task_types
  const profile = liveProfileForSlot(slot) || profileForSlot(slot)
  const taskTypes = profile?.task_types?.length ? profile.task_types : slot.target_task_types
  return taskTypes || []
}

const profileImageRef = (slot: LanAioSlot) => {
  if (slot.live_image_ref) return slot.live_image_ref
  const profile = profileForSlot(slot)
  return slot.all_in_one_image_ref || profile?.all_in_one_image_ref || '-'
}

const profileManifestKey = (slot: LanAioSlot) => {
  const profile = profileForSlot(slot)
  return slot.model_manifest_key || profile?.model_manifest_key || '-'
}

const displayProfileId = (slot: LanAioSlot) =>
  slot.live_runtime_profile || slot.configured_profile_id || slot.target_profile_id

const configuredProfileId = (slot: LanAioSlot) =>
  slot.configured_profile_id || slot.target_profile_id

const driftLabel = (slot: LanAioSlot) => {
  const reasons = slot.runtime_drift_reasons || []
  if (reasons.includes('profile')) return '类型漂移'
  if (reasons.includes('image')) return '镜像漂移'
  if (reasons.includes('task_types')) return '接单漂移'
  return '漂移'
}

const selectableReplacementTargets = (slot: LanAioSlot) =>
  (slot.replacement_targets || []).filter(target => target.selectable && target.slot_id)

const replacementDisabledReason = (reason?: string | null) => {
  if (reason === 'same_profile') return '同类型'
  if (reason === 'missing_live_profile') return '无运行态'
  return reason || ''
}

const replacementTargetLabel = (target: LanAioReplacementTarget) => {
  const gpuLabel = target.gpu_index !== null && target.gpu_index !== undefined
    ? `gpu${target.gpu_index}`
    : target.physical_slot_key || '-'
  const profile = target.live_runtime_profile || target.configured_profile_id || '-'
  const port = target.host_port ? `:${target.host_port}` : ''
  const suffix = target.selectable ? '' : ` (${replacementDisabledReason(target.disabled_reason)})`
  return `${gpuLabel}${port} / ${profile} / ${target.slot_id || '-'}${suffix}`
}

const formatOperationTime = (value?: string) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (num: number) => String(num).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

onMounted(() => {
  void loadOperations()
  refreshTimer = setInterval(() => {
    if (open.value) {
      void Promise.all([loadSlots(), loadOperations()])
    }
  }, 10000)
})

onUnmounted(() => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<template>
  <a-button type="primary" ghost @click="showModal">
    <template #icon><rocket-outlined /></template>
    LAN AIO 管理
  </a-button>

  <a-modal
    v-model:open="open"
    title="LAN AIO 管理"
    width="min(1380px, calc(100vw - 32px))"
    :z-index="1400"
    wrap-class-name="lan-aio-modal-wrap"
    :footer="null"
  >
    <div class="lan-aio-manager">
      <div class="lan-aio-toolbar">
        <div class="lan-aio-summary">
          <a-tag color="blue" class="m-0">GPU 节点 {{ nodeGroups.length }}</a-tag>
          <a-tag color="geekblue" class="m-0">物理 GPU {{ groups.length }}</a-tag>
          <a-tag color="cyan" class="m-0">AIO 类型 {{ profiles.length }}</a-tag>
          <a-tag v-if="totalRecoverableCount > 0" color="orange" class="m-0">
            可恢复 {{ totalRecoverableCount }}
          </a-tag>
          <a-tag v-if="lastInspectionAt" color="default" class="m-0">巡检 {{ lastInspectionAt }}</a-tag>
          <a-tag v-if="statusError" color="orange" class="m-0">{{ statusError }}</a-tag>
        </div>
        <div class="lan-aio-toolbar-actions">
          <a-button size="small" :loading="inspectionLoading" @click="inspectLocalServers">
            <template #icon><safety-certificate-outlined /></template>
            巡检本地服务
          </a-button>
          <a-button size="small" :disabled="nodeGroups.length === 0" @click="expandAllNodes">
            <template #icon><down-outlined /></template>
            展开全部
          </a-button>
          <a-button size="small" :disabled="nodeGroups.length === 0" @click="collapseAllNodes">
            <template #icon><right-outlined /></template>
            收起全部
          </a-button>
          <a-button size="small" :loading="loading" @click="refresh">
            <template #icon><sync-outlined /></template>
            刷新
          </a-button>
        </div>
      </div>

      <div v-if="nodeGroups.length > 0" class="lan-aio-node-list">
        <section
          v-for="nodeGroup in nodeGroups"
          :key="nodeGroup.node_key"
          class="lan-aio-node-panel"
        >
          <button
            type="button"
            class="node-panel-header"
            :aria-expanded="isNodeExpanded(nodeGroup.node_key)"
            @click="toggleNode(nodeGroup.node_key)"
          >
            <span class="node-toggle-icon">
              <down-outlined v-if="isNodeExpanded(nodeGroup.node_key)" />
              <right-outlined v-else />
            </span>
            <span class="node-heading">
              <span class="node-name">{{ nodeGroup.node_id }}</span>
              <span class="node-gpus">{{ nodeGroup.gpu_labels.join(' / ') || '-' }}</span>
            </span>
            <span class="node-metrics">
              <a-tag color="geekblue" class="m-0">GPU {{ nodeGroup.slot_groups.length }}</a-tag>
              <a-tag color="green" class="m-0">当前 {{ nodeGroup.current_count }}</a-tag>
              <a-tag color="default" class="m-0">候选 {{ nodeGroup.candidate_count }}</a-tag>
              <a-tag v-if="nodeGroup.recoverable_count > 0" color="orange" class="m-0">
                可恢复 {{ nodeGroup.recoverable_count }}
              </a-tag>
              <a-tag
                v-for="operation in activeOperationsForNode(nodeGroup)"
                :key="operation.id"
                color="blue"
                class="m-0"
              >
                {{ operation.action }}
              </a-tag>
            </span>
          </button>

          <div v-show="isNodeExpanded(nodeGroup.node_key)" class="node-panel-body">
            <div class="lan-aio-table-wrap">
              <table class="lan-aio-table">
                <colgroup>
                  <col class="lan-aio-col-physical" />
                  <col class="lan-aio-col-slot" />
                  <col class="lan-aio-col-profile" />
                  <col class="lan-aio-col-worker" />
                  <col class="lan-aio-col-cache" />
                  <col class="lan-aio-col-container" />
                  <col class="lan-aio-col-actions" />
                </colgroup>
                <thead>
                  <tr>
                    <th>GPU</th>
                    <th>Slot</th>
                    <th>AIO 类型</th>
                    <th>Worker / Control</th>
                    <th>缓存</th>
                    <th>容器</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  <template
                    v-for="slotGroup in nodeGroup.slot_groups"
                    :key="slotGroup.physical_slot_key"
                  >
                    <tr
                      v-for="(slotStatus, slotIndex) in slotGroup.slots"
                      :key="slotStatus.slot.id"
                    >
                      <td
                        v-if="slotIndex === 0"
                        :rowspan="slotGroup.slots.length"
                        class="physical-cell"
                      >
                        <div class="physical-key">{{ slotGroupGpuLabel(slotGroup) }}</div>
                        <div class="physical-meta">
                          {{ slotGroup.physical_slot_key }}
                        </div>
                        <a-tag
                          v-if="activeOperationForGroup(slotGroup)"
                          color="blue"
                          class="m-0"
                        >
                          {{ activeOperationForGroup(slotGroup)?.action }}
                        </a-tag>
                      </td>
                      <td>
                        <div class="slot-cell">
                          <span class="slot-id" :title="slotStatus.slot.id">{{ slotStatus.slot.id }}</span>
                          <div class="slot-tags">
                            <a-tag :color="slotStateColor(slotStatus)" class="m-0">
                              {{ slotStateLabel(slotStatus) }}
                            </a-tag>
                            <a-tag color="geekblue" class="m-0">{{ slotStatus.slot.phase || '-' }}</a-tag>
                            <a-tag v-if="slotStatus.slot.host_port" color="cyan" class="m-0">
                              :{{ slotStatus.slot.host_port }}
                            </a-tag>
                            <a-tag
                              v-if="switchReadinessLabel(slotStatus.slot)"
                              :color="switchReadinessColor(slotStatus.slot)"
                              class="m-0"
                            >
                              {{ switchReadinessLabel(slotStatus.slot) }}
                            </a-tag>
                            <a-tag
                              v-if="recoverReadinessLabel(slotStatus.slot)"
                              :color="recoverReadinessColor(slotStatus.slot)"
                              class="m-0"
                            >
                              {{ recoverReadinessLabel(slotStatus.slot) }}
                            </a-tag>
                          </div>
                          <div
                            v-if="
                              liveStateLabel(slotStatus.slot) ||
                              switchBlockerLabels(slotStatus.slot).length ||
                              recoverBlockerLabels(slotStatus.slot).length
                            "
                            class="slot-risk-line"
                            :title="
                              [
                                ...switchBlockerLabels(slotStatus.slot),
                                ...recoverBlockerLabels(slotStatus.slot),
                              ].join(' / ')
                            "
                          >
                            <span v-if="liveStateLabel(slotStatus.slot)">
                              {{ liveStateLabel(slotStatus.slot) }}
                            </span>
                            <span v-if="switchBlockerLabels(slotStatus.slot).length">
                              {{ switchBlockerLabels(slotStatus.slot).join(' / ') }}
                            </span>
                            <span v-if="recoverBlockerLabels(slotStatus.slot).length">
                              {{ recoverBlockerLabels(slotStatus.slot).join(' / ') }}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td>
                        <div class="profile-cell">
                          <div class="profile-title-row">
                            <span class="profile-name" :title="displayProfileId(slotStatus.slot)">
                              {{ displayProfileId(slotStatus.slot) }}
                            </span>
                            <a-tag
                              v-if="slotStatus.slot.runtime_drift"
                              color="orange"
                              class="m-0"
                            >
                              {{ driftLabel(slotStatus.slot) }}
                            </a-tag>
                          </div>
                          <span
                            v-if="configuredProfileId(slotStatus.slot) !== displayProfileId(slotStatus.slot)"
                            class="profile-config"
                            :title="configuredProfileId(slotStatus.slot)"
                          >
                            配置 {{ configuredProfileId(slotStatus.slot) }}
                          </span>
                          <span class="profile-tasks" :title="profileTaskTypes(slotStatus.slot).join(', ')">
                            {{ profileTaskTypes(slotStatus.slot).join(' + ') || '-' }}
                          </span>
                          <span class="profile-ref" :title="profileImageRef(slotStatus.slot)">
                            {{ profileImageRef(slotStatus.slot) }}
                          </span>
                          <span class="profile-ref" :title="profileManifestKey(slotStatus.slot)">
                            {{ profileManifestKey(slotStatus.slot) }}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div class="worker-cell">
                          <div class="control-row">
                            <a-tag :color="controlStateColor(slotStatus.control?.legacy)" class="m-0">
                              old {{ slotStatus.control?.legacy || '-' }}
                            </a-tag>
                            <a-tag :color="controlStateColor(slotStatus.control?.aio)" class="m-0">
                              aio {{ slotStatus.control?.aio || '-' }}
                            </a-tag>
                          </div>
                          <div v-if="slotStatus.workers?.length" class="worker-list">
                            <div
                              v-for="worker in slotStatus.workers"
                              :key="worker.agent_id"
                              class="worker-row"
                            >
                              <a-tag :color="workerStatusColor(worker.status)" class="m-0">
                                {{ worker.status || '-' }}
                              </a-tag>
                              <span class="worker-id" :title="worker.agent_id">{{ worker.agent_id }}</span>
                            </div>
                          </div>
                          <span v-else class="muted-text">暂无 heartbeat</span>
                        </div>
                      </td>
                      <td>
                        <div class="cache-cell">
                          <a-tag :color="cacheStatusColor(slotStatus.model_cache)" class="m-0">
                            {{ cacheStatusLabel(slotStatus.model_cache) }}
                          </a-tag>
                          <span class="cache-detail" :title="cacheDetail(slotStatus.model_cache)">
                            {{ cacheDetail(slotStatus.model_cache) }}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div v-if="slotStatus.remote_containers?.length" class="container-list">
                          <span
                            v-for="container in slotStatus.remote_containers"
                            :key="container"
                            class="container-line"
                            :title="container"
                          >
                            {{ container }}
                          </span>
                        </div>
                        <span v-else class="muted-text">-</span>
                      </td>
                      <td>
                        <div class="action-grid">
                          <a-tooltip
                            v-for="action in slotActions"
                            :key="action.key"
                            :title="actionDisabledReason(slotStatus, action)"
                            placement="top"
                          >
                            <a-button
                              class="action-button"
                              size="small"
                              :danger="action.danger"
                              :loading="isSlotActionLoading(slotStatus.slot.id, action.key)"
                              :disabled="isSlotActionDisabled(slotStatus, action)"
                              :aria-label="action.label"
                              @click="confirmSlotAction(slotStatus, action)"
                            >
                              <template #icon>
                                <safety-certificate-outlined v-if="action.key === 'recover'" />
                                <rocket-outlined v-else />
                              </template>
                              <span class="action-label">{{ action.label }}</span>
                            </a-button>
                          </a-tooltip>
                        </div>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
      <div v-else class="empty-cell">暂无 LAN AIO slot</div>

      <div class="lan-aio-operations">
        <div class="operations-header">
          <span>最近操作</span>
          <a-button size="small" :loading="loading" @click="loadOperations">
            <template #icon><reload-outlined /></template>
            刷新
          </a-button>
        </div>
        <div v-if="lanAioOperations.length" class="operation-list">
          <div
            v-for="operation in lanAioOperations"
            :key="operation.id"
            class="operation-row"
          >
            <span class="operation-time">
              {{ formatOperationTime(operation.started_at || operation.created_at) }}
            </span>
            <span class="operation-action">{{ operation.action }}</span>
            <span class="operation-profile">{{ operation.profile || '-' }}</span>
            <span class="operation-slot">{{ operation.slot || operation.active_lan_aio_slot || '-' }}</span>
            <a-tag :color="operationStatusColor(operation.status)" class="m-0">
              {{ operation.status || '-' }}
            </a-tag>
            <span class="operation-detail" :title="operation.error || operation.trigger_reason || '-'">
              {{ operation.error || operation.trigger_reason || '-' }}
            </span>
          </div>
        </div>
        <div v-else class="operation-empty">暂无 LAN AIO 操作</div>
      </div>
    </div>
  </a-modal>
</template>

<style scoped>
.lan-aio-manager {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.lan-aio-toolbar,
.operations-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.lan-aio-toolbar-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
}

.lan-aio-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.lan-aio-node-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lan-aio-node-panel {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #dbe4ee;
  border-radius: 6px;
  background: #ffffff;
}

.node-panel-header {
  display: grid;
  grid-template-columns: auto minmax(160px, 1fr) minmax(0, auto);
  align-items: center;
  gap: 10px;
  width: 100%;
  min-width: 0;
  padding: 10px 12px;
  border: 0;
  border-bottom: 1px solid #e5edf5;
  background: #f8fafc;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.node-panel-header[aria-expanded='false'] {
  border-bottom-color: transparent;
}

.node-toggle-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  color: #475569;
}

.node-heading {
  display: grid;
  grid-template-columns: minmax(90px, max-content) minmax(0, 1fr);
  align-items: baseline;
  gap: 10px;
  min-width: 0;
}

.node-name {
  color: #172033;
  font-size: 13px;
  font-weight: 800;
}

.node-gpus {
  min-width: 0;
  overflow: hidden;
  color: #64748b;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-metrics {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 5px;
  min-width: 0;
}

.node-metrics :deep(.ant-tag) {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-panel-body {
  min-width: 0;
  background: #ffffff;
}

.lan-aio-table-wrap {
  overflow-x: hidden;
  border: 0;
  border-radius: 0;
}

.lan-aio-table {
  width: 100%;
  min-width: 0;
  border-collapse: collapse;
  table-layout: fixed;
}

.lan-aio-col-physical {
  width: 9%;
}

.lan-aio-col-slot {
  width: 16%;
}

.lan-aio-col-profile {
  width: 18%;
}

.lan-aio-col-worker {
  width: 18%;
}

.lan-aio-col-cache {
  width: 13%;
}

.lan-aio-col-container {
  width: 11%;
}

.lan-aio-col-actions {
  width: 15%;
}

.lan-aio-table th,
.lan-aio-table td {
  min-width: 0;
  padding: 8px 7px;
  border-bottom: 1px solid #edf0f3;
  border-right: 1px solid #f1f5f9;
  vertical-align: top;
  font-size: 12px;
}

.lan-aio-table th {
  color: #475569;
  font-weight: 700;
  background: #f8fafc;
  white-space: nowrap;
}

.lan-aio-table tr:last-child td {
  border-bottom: 0;
}

.physical-cell {
  background: #fbfdff;
}

.physical-key,
.slot-id,
.profile-name {
  display: block;
  min-width: 0;
  color: #1f2937;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.profile-title-row {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.profile-title-row .profile-name {
  flex: 1 1 auto;
}

.physical-meta,
.muted-text,
.profile-tasks,
.profile-ref,
.profile-config,
.cache-detail {
  color: #64748b;
  line-height: 1.35;
}

.slot-cell,
.profile-cell,
.worker-cell,
.cache-cell,
.container-list {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
}

.slot-tags,
.control-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
}

.physical-cell :deep(.ant-tag),
.slot-tags :deep(.ant-tag),
.control-row :deep(.ant-tag),
.cache-cell :deep(.ant-tag) {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
}

.profile-tasks,
.profile-ref,
.profile-config,
.slot-risk-line,
.cache-detail,
.container-line,
.worker-id,
.operation-detail {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.slot-risk-line {
  color: #b45309;
  font-size: 12px;
}

.slot-risk-line span + span::before {
  content: ' / ';
  color: #94a3b8;
}

.worker-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.worker-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.action-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 5px;
}

.action-grid :deep(.ant-btn) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-width: 0;
  padding-inline: 6px;
  font-size: 12px;
}

.action-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:global(.takeover-confirm) {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

:global(.takeover-summary) {
  color: #475569;
  font-size: 13px;
}

:global(.takeover-policy),
:global(.takeover-blockers) {
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

:global(.takeover-blockers) {
  color: #b45309;
}

:global(.takeover-target-select) {
  width: 100%;
  min-height: 32px;
  padding: 4px 8px;
  border: 1px solid #d9d9d9;
  border-radius: 6px;
  background: #ffffff;
  color: #172033;
}

.lan-aio-operations {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 2px;
}

.operation-list {
  display: flex;
  max-height: 180px;
  flex-direction: column;
  gap: 6px;
  overflow-y: auto;
}

.operation-row {
  display: grid;
  grid-template-columns: 74px 140px 120px 180px auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 6px 8px;
  border: 1px solid #edf0f3;
  border-radius: 6px;
  color: #475569;
  font-size: 12px;
}

.operation-action,
.operation-profile,
.operation-slot,
.operation-time {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.operation-action {
  color: #1f2937;
  font-weight: 700;
}

.empty-cell,
.operation-empty {
  padding: 18px;
  color: #94a3b8;
  text-align: center;
}

@media (max-width: 720px) {
  .lan-aio-toolbar,
  .operations-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .lan-aio-toolbar-actions {
    justify-content: flex-start;
  }

  .node-panel-header {
    grid-template-columns: auto minmax(0, 1fr);
  }

  .node-heading {
    grid-template-columns: 1fr;
    gap: 2px;
  }

  .node-metrics {
    grid-column: 2;
    justify-content: flex-start;
  }

  .operation-row {
    grid-template-columns: 1fr;
  }
}

:global(.lan-aio-modal-wrap .ant-modal) {
  max-width: calc(100vw - 32px);
}

:global(.lan-aio-modal-wrap .ant-modal-body) {
  overflow-x: hidden;
}

@media (max-width: 1240px) {
  .lan-aio-table th,
  .lan-aio-table td {
    padding: 7px 6px;
  }

  .lan-aio-col-physical {
    width: 8.5%;
  }

  .lan-aio-col-slot {
    width: 16.5%;
  }

  .lan-aio-col-profile {
    width: 18.5%;
  }

  .lan-aio-col-worker {
    width: 18.5%;
  }

  .lan-aio-col-cache {
    width: 12%;
  }

  .lan-aio-col-container {
    width: 11%;
  }

  .lan-aio-col-actions {
    width: 15%;
  }

  .action-grid :deep(.ant-btn) {
    height: 24px;
    padding-inline: 6px;
  }
}

:global(.lan-aio-modal-wrap) {
  z-index: 1400 !important;
}
</style>
