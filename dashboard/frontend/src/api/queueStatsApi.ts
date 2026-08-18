import {
  cleanZombieTasks as cleanZombieTasksRaw,
  fetchConcurrencyStats as fetchConcurrencyStatsRaw,
  fetchSystemStatus as fetchSystemStatusRaw,
  fetchSystemWorkers as fetchSystemWorkersRaw,
  syncUserConcurrency as syncUserConcurrencyRaw,
} from './api'

export interface DashboardWorker {
  agent_id: string
  types: string
  provider?: string
  runtime_profile?: string
  status?: string
  control_state?: string
  runpod_locked?: boolean | number | string
  locked?: boolean | number | string
  current_task_id?: string
  current_task_type?: string
  current_task_created_at?: number | string
  current_task_progress?: number
  last_error?: string
  health_reason?: string
  consecutive_failures?: number
  quarantined_until?: number | string
  last_error_at?: number | string
  last_seen?: number | string
  [key: string]: unknown
}

export interface ConcurrencyStat {
  user_id: string | number
  [key: string]: unknown
}

export interface QueueMutationResult {
  status: string
  message?: string
  removed?: number
}

export const fetchSystemStatus = async <T>(): Promise<T> => fetchSystemStatusRaw()
export const fetchSystemWorkers = async (): Promise<{ workers?: DashboardWorker[] }> =>
  fetchSystemWorkersRaw()
export const fetchConcurrencyStats = async (): Promise<{ data?: ConcurrencyStat[] }> =>
  fetchConcurrencyStatsRaw()
export const cleanZombieTasks = async (): Promise<QueueMutationResult> => cleanZombieTasksRaw()
export const syncUserConcurrency = async (
  userId: string | number,
): Promise<QueueMutationResult> => syncUserConcurrencyRaw(userId)
