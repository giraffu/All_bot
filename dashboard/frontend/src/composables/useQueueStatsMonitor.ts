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
  active_workers: 0,
  healthy_workers: 0,
  error_workers: 0,
  quarantined_workers: 0,
  workers_by_status: {},
  comfy_online: false,
})

export function useQueueStatsMonitor() {
  const status = ref(defaultStatus())
  const workers = ref<any[]>([])
  const concurrencyStats = ref<any[]>([])
  const cleaning = ref(false)
  const syncing = ref<Record<string | number, boolean>>({})

  let timer: ReturnType<typeof setInterval> | null = null
  let tick = 0

  const queueByTypeDisplay = computed(() => {
    if (!status.value.queue_by_type || Object.keys(status.value.queue_by_type).length === 0) {
      return []
    }

    return Object.entries(status.value.queue_by_type).map(([type, count]) => ({
      type,
      count,
    }))
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

      if (tick % 5 === 0) {
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
    }, 1000)
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
    cleanZombies,
    syncLock,
    updateQueue,
  }
}
