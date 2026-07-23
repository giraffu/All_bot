import type { TaskType } from '@/types'

export function quotePoints(
  taskType: TaskType,
  multiplier: number,
  durationSeconds: number | null,
): number {
  if (taskType === 'image_upscale') return multiplier === 4 ? 4 : 2
  const units = Math.ceil((durationSeconds || 0) / 10)
  if (taskType === 'video_upscale') return units * 5
  return units * (multiplier === 4 ? 5 : 3)
}
