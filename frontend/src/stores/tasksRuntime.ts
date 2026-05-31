import {
  applyTaskResultErrorToTask,
  applyTaskResultResponseToTask,
  restorePersistedTask,
  type TaskResultResponsePayload
} from './taskResultState.ts'
import type { TaskExtraOutputs } from '@/types/gallery'

export interface RuntimeTaskLike {
  id: string
  title: string
  progress: number
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
  resultUrl?: string
  extraOutputs?: TaskExtraOutputs
  error?: string
  awaitingResult?: boolean
  updatedAt?: number
}

export interface RuntimeStorageLike {
  getItem(key: string): string | null
}

export interface PollTaskResultDeps<T extends RuntimeTaskLike> {
  apiGet: (url: string) => Promise<{ data: unknown }>
  schedule: (callback: () => void, delayMs: number) => void
  onSuccess?: (task: T) => void
  onTimeout?: (task: T) => void
  onForbidden?: (task: T) => void
  onError?: (task: T) => void
  onRequestError?: (error: unknown) => void
}

export interface ProbeDetachedTaskResultDeps<T extends RuntimeTaskLike> {
  apiGet: (url: string) => Promise<{ data: unknown }>
  schedule: (callback: () => void, delayMs: number) => void
  onResolved?: (task: T) => void
  onPending?: (task: T) => void
  onForbidden?: (task: T) => void
  onExhausted?: (task: T) => void
  onRequestError?: (error: unknown) => void
}

export interface RestoreTasksDeps<T extends RuntimeTaskLike> {
  startListening: (task: T) => void
  pollForResult: (task: T) => void
  onParseError?: (error: unknown) => void
}

export interface PersistableTaskLike extends RuntimeTaskLike {
  eventSource?: unknown
}

export const STALE_ACTIVE_TASK_TTL_MS = 24 * 60 * 60 * 1000

export function touchTaskActivity<T extends RuntimeTaskLike>(
  task: T,
  now = Date.now()
): T {
  task.updatedAt = now
  return task
}

function hydrateStoredTask<T extends RuntimeTaskLike>(task: T, now: number): T {
  if (typeof task.updatedAt === 'number') {
    return task
  }

  return {
    ...task,
    updatedAt: now
  }
}

export function serializeTasksForStorage<T extends PersistableTaskLike>(
  tasks: T[],
  now = Date.now()
): Array<Omit<T, 'eventSource'> & { updatedAt: number }> {
  return tasks.map(({ eventSource: _eventSource, ...task }) => ({
    ...task,
    updatedAt: typeof task.updatedAt === 'number' ? task.updatedAt : now
  }))
}

function isStaleActiveTask(task: RuntimeTaskLike, now: number): boolean {
  if (task.awaitingResult) {
    return false
  }

  if (task.status !== 'pending' && task.status !== 'running') {
    return false
  }

  if (typeof task.updatedAt !== 'number') {
    return false
  }

  return now - task.updatedAt > STALE_ACTIVE_TASK_TTL_MS
}

export async function pollTaskResult<T extends RuntimeTaskLike>(
  task: T,
  activeTasks: T[],
  deps: PollTaskResultDeps<T>,
  retryCount = 0
): Promise<void> {
  const currentTask = activeTasks.find(t => t.id === task.id)
  if (!currentTask) return

  try {
    const res = await deps.apiGet(`/tasks/${task.id}/result`)
    const transition = applyTaskResultResponseToTask(
      currentTask,
      res.data as Parameters<typeof applyTaskResultResponseToTask<T>>[1],
      retryCount,
      10
    )
    Object.assign(currentTask, touchTaskActivity(transition.task))

    if (transition.type === 'resolved') {
      deps.onSuccess?.(currentTask)
      return
    }

    if (transition.type === 'retry') {
      deps.schedule(() => {
        void pollTaskResult(
          task,
          activeTasks,
          deps,
          transition.nextRetryCount ?? retryCount + 1
        )
      }, 1500)
      return
    }

    deps.onTimeout?.(currentTask)
  } catch (error: any) {
    deps.onRequestError?.(error)
    const transition = applyTaskResultErrorToTask(
      currentTask,
      error?.response?.status,
      retryCount,
      10
    )
    Object.assign(currentTask, touchTaskActivity(transition.task))

    if (transition.type === 'forbidden') {
      deps.onForbidden?.(currentTask)
      return
    }

    if (transition.type === 'retry') {
      deps.schedule(() => {
        void pollTaskResult(
          task,
          activeTasks,
          deps,
          transition.nextRetryCount ?? retryCount + 1
        )
      }, 1500)
      return
    }

    deps.onError?.(currentTask)
  }
}

export async function probeDetachedTaskResult<T extends RuntimeTaskLike>(
  task: T,
  activeTasks: T[],
  deps: ProbeDetachedTaskResultDeps<T>,
  retryCount = 0,
  maxRetries = 120,
  delayMs = 5_000
): Promise<void> {
  const currentTask = activeTasks.find(t => t.id === task.id)
  if (!currentTask) return

  if (currentTask.status === 'cancelled' || currentTask.status === 'failed') {
    return
  }

  if (currentTask.status === 'success' && currentTask.resultUrl) {
    return
  }

  const scheduleRetry = (nextRetryCount = retryCount + 1) => {
    deps.schedule(() => {
      void probeDetachedTaskResult(
        task,
        activeTasks,
        deps,
        nextRetryCount,
        maxRetries,
        delayMs
      )
    }, delayMs)
  }

  try {
    const res = await deps.apiGet(`/tasks/${task.id}/result`)
    const payload = res.data as TaskResultResponsePayload

    if (payload.status === 'success' && payload.result_url) {
      Object.assign(currentTask, touchTaskActivity({
        ...currentTask,
        progress: 100,
        status: 'success',
        resultUrl: payload.result_url,
        extraOutputs: payload.extra_outputs ?? {},
        resultMeta: payload.result_meta ?? {},
        awaitingResult: false,
        error: undefined
      }))
      deps.onResolved?.(currentTask)
      return
    }

    touchTaskActivity(currentTask)

    if (payload.status === 'pending_result' && retryCount < maxRetries) {
      deps.onPending?.(currentTask)
      scheduleRetry()
      return
    }

    if (payload.status === 'pending_result') {
      deps.onExhausted?.(currentTask)
      return
    }

    if (retryCount < maxRetries) {
      scheduleRetry()
      return
    }

    deps.onExhausted?.(currentTask)
  } catch (error: any) {
    deps.onRequestError?.(error)

    if (error?.response?.status === 403) {
      Object.assign(currentTask, touchTaskActivity({
        ...currentTask,
        status: 'failed',
        awaitingResult: false,
        error: '任务不存在或无权限'
      }))
      deps.onForbidden?.(currentTask)
      return
    }

    touchTaskActivity(currentTask)
    if (retryCount < maxRetries) {
      scheduleRetry()
      return
    }

    deps.onExhausted?.(currentTask)
  }
}

export function restoreTasksFromStorage<T extends RuntimeTaskLike>(
  storage: RuntimeStorageLike,
  activeTasks: T[],
  deps: RestoreTasksDeps<T>,
  now = Date.now()
): void {
  const storedTasks = storage.getItem('active_tasks')
  if (!storedTasks) return

  try {
    const parsed = (JSON.parse(storedTasks) as T[])
      .map(task => hydrateStoredTask(task, now))
      .filter(task => !isStaleActiveTask(task, now))
    activeTasks.splice(0, activeTasks.length, ...parsed)

    activeTasks.forEach(task => {
      const restoration = restorePersistedTask(task)
      Object.assign(task, restoration.task)

      if (restoration.type === 'poll_result') {
        deps.pollForResult(task)
      } else if (restoration.type === 'resume_sse') {
        deps.startListening(task)
      }
    })
  } catch (error) {
    deps.onParseError?.(error)
  }
}
