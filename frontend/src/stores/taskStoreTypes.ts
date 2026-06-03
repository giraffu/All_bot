import type { TaskExtraOutputs, Wan22ResultMeta } from '@/types/gallery'

export type TaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
export type TaskRefundStatus = 'pending' | 'refunded' | 'unconfirmed'

export interface TaskProgressPayload {
  status?: TaskStatus
  progress?: number
  queue_pos?: number | null
  error?: string
  message?: string
  task_id?: string
  task_type?: string | null
  media_type?: string | null
  result_url?: string
  extra_outputs?: TaskExtraOutputs
  result_meta?: Wan22ResultMeta
  [key: string]: unknown
}

export interface TaskStreamHandle {
  close: () => void
}

export interface Task {
  id: string
  type: string
  title: string
  progress: number
  status: TaskStatus
  queuePos?: number
  resultUrl?: string
  extraOutputs?: TaskExtraOutputs
  resultMeta?: Wan22ResultMeta
  error?: string
  eventSource?: TaskStreamHandle
  retryCount?: number
  awaitingResult?: boolean
  updatedAt?: number
  cancelRequested?: boolean
  cancelMessage?: string
  cancelCreditBaseline?: number | null
  refundStatus?: TaskRefundStatus
  refundMessage?: string
}
