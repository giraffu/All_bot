import type { TaskExtraOutputs, Wan22ResultMeta } from '@/types/gallery'

export type TaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
export type TaskRefundStatus = 'pending' | 'refunded' | 'unconfirmed'

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
