export type FloatingTaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled'

export interface FloatingTaskSlotLike {
  id: string
  status: FloatingTaskStatus
  updatedAt?: number
}

export const MAX_FLOATING_TASKS = 3

export function isTerminalFloatingTask(task: Pick<FloatingTaskSlotLike, 'status'>): boolean {
  return task.status === 'success' || task.status === 'failed' || task.status === 'cancelled'
}

export function countBlockingFloatingTasks(
  tasks: Array<Pick<FloatingTaskSlotLike, 'status'>>
): number {
  return tasks.filter(task => !isTerminalFloatingTask(task)).length
}

export function getOldestTerminalFloatingTaskIdsForNewTask(
  tasks: FloatingTaskSlotLike[],
  limit = MAX_FLOATING_TASKS
): string[] {
  const slotsNeeded = Math.max(tasks.length - limit + 1, 0)
  if (slotsNeeded === 0) {
    return []
  }

  return tasks
    .filter(isTerminalFloatingTask)
    .sort((left, right) => (left.updatedAt ?? 0) - (right.updatedAt ?? 0))
    .slice(0, slotsNeeded)
    .map(task => task.id)
}
