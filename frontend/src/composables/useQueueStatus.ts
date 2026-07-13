import { ref } from 'vue'
import api from '@/api'

interface QueueStatusData {
  comfy_online: boolean
  queue_size: number
  queue_by_type: Record<string, number>
}

interface QueueStatusState {
  loading: boolean
  isFirstLoad: boolean
  data: QueueStatusData
}

export function useQueueStatus() {
  const queueStatus = ref<QueueStatusState>({
    loading: false,
    isFirstLoad: true,
    data: {
      comfy_online: false,
      queue_size: 0,
      queue_by_type: {}
    }
  })

  const fetchQueueStatus = async () => {
    queueStatus.value.loading = true
    try {
      const res = await api.get('/tasks/queue-status')
      queueStatus.value.data = res.data
    } catch (error) {
      console.error('Failed to fetch queue status', error)
    } finally {
      queueStatus.value.loading = false
      queueStatus.value.isFirstLoad = false
    }
  }

  return {
    queueStatus,
    fetchQueueStatus
  }
}
