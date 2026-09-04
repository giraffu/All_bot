import { TASK_TYPE_COLORS, TASK_TYPE_LABELS } from '../constants/taskTypes'

type CreditDistributionResponse = {
  values?: Record<string, number>
}

type EfficiencyItem = {
  value: number
  credits: number
  gpu_hours: number
  task_count: number
  estimated: boolean
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
  gpuHours: number
  taskCount: number
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
  gpuHours: Number(item.gpu_hours || 0),
  taskCount: Number(item.task_count || 0),
  estimated: Boolean(item.estimated),
  itemStyle: { color: taskColor(taskType) },
}))
