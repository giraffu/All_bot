import type { Task } from './taskStoreTypes'

export type ExternalTaskOutcome =
  | { status: 'success'; resultUrl?: string }
  | { status: 'failed'; error: string }

export function createPendingTask(taskId: string, type: string, title: string): Task {
  return {
    id: taskId,
    type,
    title,
    progress: 0,
    status: 'pending',
    updatedAt: Date.now(),
  }
}

export function resetExistingTaskSession(task: Task, type: string, title: string): void {
  task.type = type
  task.title = title
  task.status = task.status === 'failed' || task.status === 'cancelled'
    ? 'pending'
    : task.status
  task.cancelRequested = false
  task.cancelMessage = undefined
  task.refundStatus = undefined
  task.refundMessage = undefined
}

export function settleExternalTaskSession(
  task: Task,
  outcome: ExternalTaskOutcome,
): void {
  task.status = outcome.status
  task.progress = outcome.status === 'success' ? 100 : 0
  task.awaitingResult = false
  task.queuePos = undefined
  task.cancelRequested = false
  task.cancelMessage = undefined
  task.refundStatus = undefined
  task.refundMessage = undefined

  if (outcome.status === 'success') {
    task.resultUrl = outcome.resultUrl
    task.error = undefined
  } else {
    task.resultUrl = undefined
    task.error = outcome.error
  }
}

export function removeTaskSession(
  tasks: Task[],
  taskId: string,
  closeTaskStream: (task: Task) => void,
): void {
  const index = tasks.findIndex(task => task.id === taskId)
  if (index === -1) {
    return
  }
  closeTaskStream(tasks[index])
  tasks.splice(index, 1)
}

export function clearCompletedTaskSessions(
  tasks: Task[],
  removeTask: (taskId: string) => void,
): void {
  tasks
    .filter(task => (
      task.status === 'success'
      || task.status === 'failed'
      || task.status === 'cancelled'
    ))
    .forEach(task => removeTask(task.id))
}
