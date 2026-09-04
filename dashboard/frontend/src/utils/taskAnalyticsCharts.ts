import { TASK_TYPE_COLORS, TASK_TYPE_LABELS } from '../constants/taskTypes'

type CreditDistributionResponse = {
  values?: Record<string, number>
}

type EfficiencyItem = {
  value: number
  credits: number
  gross_credits: number
  gpu_hours: number
  task_count: number
  successful_task_count: number
  worker_count: number
  telemetry_coverage: number
  estimated: boolean
  gpu_time_source: string
}

type GpuEfficiencyResponse = {
  items?: Record<string, EfficiencyItem>
}

type BasePieSlice = {
  taskType: string
  name: string
  value: number
  itemStyle: { color?: string }
}

export type CreditPieSlice = BasePieSlice

export type GpuEfficiencyPieSlice = BasePieSlice & {
  credits: number
  grossCredits: number
  gpuHours: number
  taskCount: number
  successfulTaskCount: number
  workerCount: number
  telemetryCoverage: number
  estimated: boolean
}

const taskLabel = (taskType: string) => (
  (TASK_TYPE_LABELS as Record<string, string>)[taskType] || taskType
)

const taskColor = (taskType: string) => (
  (TASK_TYPE_COLORS as Record<string, string>)[taskType] || undefined
)

export const buildCreditConsumptionPieData = (
  response: CreditDistributionResponse | undefined,
): CreditPieSlice[] => Object.entries(response?.values || {}).map(([taskType, value]) => ({
  taskType,
  name: taskLabel(taskType),
  value: Number(value || 0),
  itemStyle: { color: taskColor(taskType) },
}))

export const buildGpuEfficiencyPieData = (
  response: GpuEfficiencyResponse | undefined,
): GpuEfficiencyPieSlice[] => Object.entries(response?.items || {}).map(([taskType, item]) => ({
  taskType,
  name: taskLabel(taskType),
  value: Number(item.value || 0),
  credits: Number(item.credits || 0),
  grossCredits: Number(item.gross_credits || 0),
  gpuHours: Number(item.gpu_hours || 0),
  taskCount: Number(item.task_count || 0),
  successfulTaskCount: Number(item.successful_task_count || 0),
  workerCount: Number(item.worker_count || 0),
  telemetryCoverage: Number(item.telemetry_coverage || 0),
  estimated: Boolean(item.estimated),
  itemStyle: { color: taskColor(taskType) },
}))
