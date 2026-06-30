import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  cleanZombieTasks,
  fetchConcurrencyStats,
  fetchSystemStatus,
  fetchSystemWorkers,
  syncUserConcurrency,
} from '../api/api'

const defaultStatus = () => ({
  queue_size: 0,
  queue_by_type: {},
  queue_by_type_details: {},
  active_workers: 0,
  healthy_workers: 0,
  error_workers: 0,
  quarantined_workers: 0,
  workers_by_status: {},
  comfy_online: false,
  runpod_profile_queue_details: [],
  low_trust_free_tier_pending_user_count: 0,
  low_trust_free_tier_pending_task_count: 0,
})

const queueRefreshIntervalMs = 10000
const concurrencyRefreshTicks = 6

export function useQueueStatsMonitor() {
  const status = ref(defaultStatus())
  const workers = ref<any[]>([])
  const concurrencyStats = ref<any[]>([])
  const cleaning = ref(false)
  const syncing = ref<Record<string | number, boolean>>({})

  let timer: ReturnType<typeof setInterval> | null = null
  let tick = 0

  const queueByTypeDisplay = computed(() => {
    const queueByType = status.value.queue_by_type || {}
    const queueByTypeDetails = status.value.queue_by_type_details || {}
    const taskTypes = Array.from(
      new Set([...Object.keys(queueByType), ...Object.keys(queueByTypeDetails)])
    )

    if (taskTypes.length === 0) {
      return []
    }

    return taskTypes
      .map((type) => {
        const detail = queueByTypeDetails[type] || {}
        const rawWaitSeconds = detail.max_pending_wait_seconds
        const maxPendingWaitSeconds =
          rawWaitSeconds === null || rawWaitSeconds === undefined
            ? null
            : Number(rawWaitSeconds)
        const rawNonLowTrustWaitSeconds =
          detail.max_non_low_trust_pending_wait_seconds
        const maxNonLowTrustPendingWaitSeconds =
          rawNonLowTrustWaitSeconds === null ||
          rawNonLowTrustWaitSeconds === undefined
            ? null
            : Number(rawNonLowTrustWaitSeconds)

        return {
          type,
          count: Number(detail.active_count ?? queueByType[type] ?? 0),
          activeCount: Number(detail.active_count ?? queueByType[type] ?? 0),
          pendingCount: Number(detail.pending_count ?? 0),
          lowTrustFreeTierUserCount: Number(
            detail.low_trust_free_tier_user_count ?? 0
          ),
          lowTrustFreeTierTaskCount: Number(
            detail.low_trust_free_tier_task_count ?? 0
          ),
          maxPendingWaitSeconds: Number.isFinite(maxPendingWaitSeconds)
            ? maxPendingWaitSeconds
            : null,
          maxNonLowTrustPendingWaitSeconds: Number.isFinite(
            maxNonLowTrustPendingWaitSeconds
          )
            ? maxNonLowTrustPendingWaitSeconds
            : null,
          oldestPendingTaskId: detail.oldest_pending_task_id || null,
          oldestPendingCreatedAt: detail.oldest_pending_created_at || null,
        }
      })
      .sort((a, b) => {
        const waitA = a.maxPendingWaitSeconds ?? -1
        const waitB = b.maxPendingWaitSeconds ?? -1
        if (waitA !== waitB) {
          return waitB - waitA
        }
        if (a.activeCount !== b.activeCount) {
          return b.activeCount - a.activeCount
        }
        return a.type.localeCompare(b.type)
      })
  })

  const runpodProfileQueueDisplay = computed(() => {
    const rawDetails = (status.value as any).runpod_profile_queue_details || []

    return rawDetails.map((item: any) => {
      const rawWaitSeconds = item.max_pending_wait_seconds
      const maxPendingWaitSeconds =
        rawWaitSeconds === null || rawWaitSeconds === undefined
          ? null
          : Number(rawWaitSeconds)
      const rawNonLowTrustWaitSeconds =
        item.max_non_low_trust_pending_wait_seconds
      const maxNonLowTrustPendingWaitSeconds =
        rawNonLowTrustWaitSeconds === null ||
        rawNonLowTrustWaitSeconds === undefined
          ? null
          : Number(rawNonLowTrustWaitSeconds)

      return {
        profile: item.profile,
        label: item.label,
        autoscalerEnabled: item.autoscaler_enabled !== false,
        supportedTaskTypes: Array.isArray(item.supported_task_types)
          ? item.supported_task_types
          : [],
        activeCount: Number(item.active_count || 0),
        pendingCount: Number(item.pending_count || 0),
        activeCountByTaskType: item.active_count_by_task_type || {},
        pendingCountByTaskType: item.pending_count_by_task_type || {},
        maxPendingWaitSeconds: Number.isFinite(maxPendingWaitSeconds)
          ? maxPendingWaitSeconds
          : null,
        maxNonLowTrustPendingWaitSeconds: Number.isFinite(
          maxNonLowTrustPendingWaitSeconds
        )
          ? maxNonLowTrustPendingWaitSeconds
          : null,
        oldestPendingTaskId: item.oldest_pending_task_id || null,
        oldestPendingCreatedAt: item.oldest_pending_created_at || null,
      }
    })
  })

  const loadConcurrencyStats = async () => {
    const concurrencyData = await fetchConcurrencyStats()
    if (concurrencyData?.data) {
      concurrencyStats.value = concurrencyData.data
    }
  }

  const updateQueue = async () => {
    try {
      const [statusData, workersData] = await Promise.all([
        fetchSystemStatus(),
        fetchSystemWorkers(),
      ])

      if (statusData) {
        status.value = statusData
      }

      if (workersData?.workers) {
        workers.value = workersData.workers
      }

      if (tick % concurrencyRefreshTicks === 0) {
        await loadConcurrencyStats()
      }
      tick += 1
    } catch (err) {
      console.error('Error fetching system status:', err)
    }
  }

  const syncLock = async (userId: string | number) => {
    syncing.value = {
      ...syncing.value,
      [userId]: true,
    }

    try {
      const res = await syncUserConcurrency(userId)
      if (res.status === 'success') {
        await loadConcurrencyStats()
      }
      return res
    } finally {
      syncing.value = {
        ...syncing.value,
        [userId]: false,
      }
    }
  }

  const cleanZombies = async () => {
    cleaning.value = true
    try {
      const res = await cleanZombieTasks()
      if (res.status === 'success') {
        await updateQueue()
      }
      return res
    } finally {
      cleaning.value = false
    }
  }

  onMounted(() => {
    void updateQueue()
    timer = setInterval(() => {
      void updateQueue()
    }, queueRefreshIntervalMs)
  })

  onUnmounted(() => {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  })

  return {
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
  }
}
