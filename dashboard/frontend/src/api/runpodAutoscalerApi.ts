import {
  fetchRunPodAutoscaler as fetchRunPodAutoscalerRaw,
  fetchRunPodOperations as fetchRunPodOperationsRaw,
  updateRunPodAutoscalerSettings as updateRunPodAutoscalerSettingsRaw,
} from './api'

export interface RunPodAutoscalerConfig {
  scale_up_wait_seconds_by_profile?: Record<string, number>
  task_duration_seconds_by_type?: Record<string, number>
  paused_profiles?: string[]
  profile_autoscaler_paused_by_profile?: Record<string, boolean>
}

export interface RunPodDecision {
  profile?: string
  reason?: string
  capacity_status?: string
  non_low_trust_clear_pending_count?: number
  estimated_non_low_trust_clear_time_seconds?: number | null
  estimated_clear_time_seconds?: number | null
  [key: string]: unknown
}

export interface RunPodOperation {
  id?: string | number
  action?: string
  profile?: string
  source?: string
  status?: string
  slot?: string
  cleanup_slots?: string[]
  requested_count?: number
  error?: string
  trigger_reason?: string
  log_tail?: string[]
  started_at?: string | number
  created_at?: string | number
}

export interface RunPodAutoscalerPayload {
  config?: RunPodAutoscalerConfig
  decisions?: RunPodDecision[]
}

export const fetchRunPodAutoscaler = async (): Promise<RunPodAutoscalerPayload> =>
  fetchRunPodAutoscalerRaw()
export const fetchRunPodOperations = async (): Promise<{ operations?: RunPodOperation[] }> =>
  fetchRunPodOperationsRaw()
export const updateRunPodAutoscalerSettings = async (
  payload: Record<string, unknown>,
): Promise<RunPodAutoscalerPayload> => updateRunPodAutoscalerSettingsRaw(payload)
