export type FloatingTaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled'

export interface FloatingTaskSlotLike {
  id: string
  status: FloatingTaskStatus
  updatedAt?: number
}

export const COMPACT_FLOATING_TASK_SLOTS = 3

export function isTerminalFloatingTask(task: Pick<FloatingTaskSlotLike, 'status'>): boolean {
  return task.status === 'success' || task.status === 'failed' || task.status === 'cancelled'
}

export function getOldestTerminalFloatingTaskIdsForNewTask(
  tasks: FloatingTaskSlotLike[],
  compactSlots = COMPACT_FLOATING_TASK_SLOTS
): string[] {
  const slotsNeeded = Math.max(tasks.length - compactSlots + 1, 0)
  if (slotsNeeded === 0) {
    return []
  }

  return tasks
    .filter(isTerminalFloatingTask)
    .sort((left, right) => (left.updatedAt ?? 0) - (right.updatedAt ?? 0))
    .slice(0, slotsNeeded)
    .map(task => task.id)
}
