<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  ReloadOutlined,
  RocketOutlined,
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
}

type LanAioSlotGroup = {
  physical_slot_key: string
  active_slot_id?: string | null
  active_slot_source?: string | null
  node_id?: string
  gpu_index?: number | null
  slots: LanAioSlotStatus[]
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

type LanAioActionKey = 'takeover'

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
]

const open = ref(false)
const loading = ref(false)
const slotActionLoading = ref<Set<string>>(new Set())
const profiles = ref<LanAioProfile[]>([])
const groups = ref<LanAioSlotGroup[]>([])
const operations = ref<RunPodOperation[]>([])
const statusError = ref('')
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
  profileById.value.get(slot.target_profile_id)

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

const isSlotActionDisabled = (slotStatus: LanAioSlotStatus, action: LanAioAction) =>
  isSlotLocked(slotStatus.slot) || (action.key === 'takeover' && isCurrentSlot(slotStatus))

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

const showModal = async () => {
  open.value = true
  await refresh()
}

const actionLabel = (action: string) =>
  slotActions.find(item => item.key === action)?.label || action

const submitSlotAction = async (slot: LanAioSlot, action: LanAioActionKey) => {
  setSlotActionLoading(slot.id, action, true)
  try {
    await startLanAioSlotAction(slot.id, action, {
      reason: `dashboard lan aio ${action}`,
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

const confirmSlotAction = (slotStatus: LanAioSlotStatus, action: LanAioAction) => {
  const slot = slotStatus.slot
  Modal.confirm({
    title: `${action.label}：${slot.id}`,
    content: `${slotPhysicalKey(slot)} / ${slot.target_profile_id}`,
    zIndex: 1800,
    centered: true,
    width: 480,
    getContainer: () => document.body,
    okText: action.label,
    okType: action.danger ? 'danger' : 'primary',
    cancelText: '取消',
    onOk: () => submitSlotAction(slot, action.key),
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
  const profile = profileForSlot(slot)
  const taskTypes = profile?.task_types?.length ? profile.task_types : slot.target_task_types
  return taskTypes || []
}

const profileImageRef = (slot: LanAioSlot) => {
  const profile = profileForSlot(slot)
  return slot.all_in_one_image_ref || profile?.all_in_one_image_ref || '-'
}

const profileManifestKey = (slot: LanAioSlot) => {
  const profile = profileForSlot(slot)
  return slot.model_manifest_key || profile?.model_manifest_key || '-'
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
          <a-tag color="blue" class="m-0">物理 GPU {{ groups.length }}</a-tag>
          <a-tag color="cyan" class="m-0">AIO 类型 {{ profiles.length }}</a-tag>
          <a-tag v-if="statusError" color="orange" class="m-0">{{ statusError }}</a-tag>
        </div>
        <a-button size="small" :loading="loading" @click="refresh">
          <template #icon><sync-outlined /></template>
          刷新
        </a-button>
      </div>

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
              <th>节点/GPU</th>
              <th>Slot</th>
              <th>AIO 类型</th>
              <th>Worker / Control</th>
              <th>缓存</th>
              <th>容器</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody v-if="groups.length > 0">
            <template v-for="group in groups" :key="group.physical_slot_key">
              <tr
                v-for="(slotStatus, slotIndex) in group.slots"
                :key="slotStatus.slot.id"
              >
                <td v-if="slotIndex === 0" :rowspan="group.slots.length" class="physical-cell">
                  <div class="physical-key">{{ group.physical_slot_key }}</div>
                  <div class="physical-meta">
                    {{ group.node_id || '-' }} / gpu{{ group.gpu_index ?? '-' }}
                  </div>
                  <a-tag
                    v-if="activeOperationForSlot(slotStatus.slot)"
                    color="blue"
                    class="m-0"
                  >
                    {{ activeOperationForSlot(slotStatus.slot)?.action }}
                  </a-tag>
                </td>
                <td>
                  <div class="slot-cell">
                    <span class="slot-id" :title="slotStatus.slot.id">{{ slotStatus.slot.id }}</span>
                    <div class="slot-tags">
                      <a-tag :color="isCurrentSlot(slotStatus) ? 'green' : 'default'" class="m-0">
                        {{ isCurrentSlot(slotStatus) ? '当前' : '候选' }}
                      </a-tag>
                      <a-tag color="geekblue" class="m-0">{{ slotStatus.slot.phase || '-' }}</a-tag>
                      <a-tag v-if="slotStatus.slot.host_port" color="cyan" class="m-0">
                        :{{ slotStatus.slot.host_port }}
                      </a-tag>
                    </div>
                  </div>
                </td>
                <td>
                  <div class="profile-cell">
                    <span class="profile-name" :title="slotStatus.slot.target_profile_id">
                      {{ slotStatus.slot.target_profile_id }}
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
                      :title="action.label"
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
                          <rocket-outlined />
                        </template>
                        <span class="action-label">{{ action.label }}</span>
                      </a-button>
                    </a-tooltip>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
          <tbody v-else>
            <tr>
              <td colspan="7" class="empty-cell">暂无 LAN AIO slot</td>
            </tr>
          </tbody>
        </table>
      </div>

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

.lan-aio-summary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.lan-aio-table-wrap {
  overflow-x: hidden;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
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

.physical-meta,
.muted-text,
.profile-tasks,
.profile-ref,
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
