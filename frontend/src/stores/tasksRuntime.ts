import {
  applyTaskResultErrorToTask,
  applyTaskResultResponseToTask,
  restorePersistedTask,
  type TaskResultResponsePayload
} from './taskResultState.ts'
import type { TaskExtraOutputs } from '@/types/gallery'

export type RuntimeTaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled'

export interface RuntimeTaskLike {
  id: string
  title: string
  progress: number
  status: RuntimeTaskStatus
  resultUrl?: string
  extraOutputs?: TaskExtraOutputs
  queuePos?: number
  error?: string
  awaitingResult?: boolean
  updatedAt?: number
  cancelMessage?: string
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

export interface TaskStatusResponsePayload {
  status?: RuntimeTaskStatus
  task_id?: string
  task_type?: string | null
  media_type?: string | null
  queue_pos?: number | string | null
  error?: string
  message?: string
}

export interface PollTaskStatusDeps<T extends RuntimeTaskLike> {
  apiGet: (url: string) => Promise<{ data: unknown }>
  schedule: (callback: () => void, delayMs: number) => void
  pollForResult: (task: T) => void
  finalizeCancelledTask: (task: T, cancelMessage?: string) => void
  notifyTaskFailure: (task: T) => void
  handleUnauthorized?: () => void
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
  startStatusPolling: (task: T) => void
  pollForResult: (task: T) => void
  onParseError?: (error: unknown) => void
}

export interface PersistableTaskLike extends RuntimeTaskLike {
  eventSource?: unknown
}

export const STALE_ACTIVE_TASK_TTL_MS = 24 * 60 * 60 * 1000
export const POLL_TASK_RESULT_MAX_RETRIES = 120
export const POLL_TASK_RESULT_RETRY_DELAY_MS = 1500
export const POLL_TASK_STATUS_INTERVAL_MS = 15_000

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
      POLL_TASK_RESULT_MAX_RETRIES
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
      }, POLL_TASK_RESULT_RETRY_DELAY_MS)
      return
    }

    deps.onTimeout?.(currentTask)
  } catch (error: any) {
    deps.onRequestError?.(error)
    const transition = applyTaskResultErrorToTask(
      currentTask,
      error?.response?.status,
      retryCount,
      POLL_TASK_RESULT_MAX_RETRIES
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
      }, POLL_TASK_RESULT_RETRY_DELAY_MS)
      return
    }

    deps.onError?.(currentTask)
  }
}

function normalizeQueuePosition(queuePos: number | string | null | undefined): number | undefined {
  if (queuePos === null || queuePos === undefined || queuePos === '') {
    return undefined
  }
  const parsed = Number(queuePos)
  if (!Number.isFinite(parsed)) {
    return undefined
  }
  return parsed
}

function applyTaskStatusPayload<T extends RuntimeTaskLike>(
  task: T,
  payload: TaskStatusResponsePayload
): T {
  if (payload.status === 'pending') {
    return touchTaskActivity({
      ...task,
      status: 'pending',
      queuePos: normalizeQueuePosition(payload.queue_pos),
      awaitingResult: false,
      error: undefined
    })
  }

  if (payload.status === 'running') {
    return touchTaskActivity({
      ...task,
      status: 'running',
      queuePos: undefined,
      awaitingResult: false,
      error: undefined
    })
  }

  if (payload.status === 'success') {
    return touchTaskActivity({
      ...task,
      status: 'running',
      queuePos: undefined,
      awaitingResult: true,
      error: undefined
    })
  }

  if (payload.status === 'failed') {
    return touchTaskActivity({
      ...task,
      status: 'failed',
      queuePos: undefined,
      awaitingResult: false,
      error: payload.error || '未知错误'
    })
  }

  if (payload.status === 'cancelled') {
    return touchTaskActivity({
      ...task,
      status: 'cancelled',
      queuePos: undefined,
      awaitingResult: false,
      error: undefined,
      cancelMessage: payload.message || payload.error || task.cancelMessage
    })
  }

  return touchTaskActivity(task)
}

export async function pollTaskStatus<T extends RuntimeTaskLike>(
  task: T,
  activeTasks: T[],
  deps: PollTaskStatusDeps<T>,
): Promise<void> {
  const currentTask = activeTasks.find(t => t.id === task.id)
  if (!currentTask) return

  if (
    currentTask.status === 'success'
    || currentTask.status === 'failed'
    || currentTask.status === 'cancelled'
  ) {
    return
  }

  try {
    const res = await deps.apiGet(`/tasks/${task.id}/status`)
    const payload = res.data as TaskStatusResponsePayload
    Object.assign(currentTask, applyTaskStatusPayload(currentTask, payload))

    if (payload.status === 'success') {
      deps.pollForResult(currentTask)
      return
    }

    if (payload.status === 'failed') {
      deps.notifyTaskFailure(currentTask)
      return
    }

    if (payload.status === 'cancelled') {
      deps.finalizeCancelledTask(currentTask, payload.message || payload.error)
      return
    }
  } catch (error: any) {
    deps.onRequestError?.(error)
    if (error?.response?.status === 401) {
      deps.handleUnauthorized?.()
      return
    }
    if (error?.response?.status === 403 || error?.response?.status === 404) {
      currentTask.status = 'failed'
      currentTask.queuePos = undefined
      currentTask.awaitingResult = false
      currentTask.error = '任务不存在或无权限'
      touchTaskActivity(currentTask)
      deps.notifyTaskFailure(currentTask)
      return
    }
  }

  deps.schedule(() => {
    void pollTaskStatus(task, activeTasks, deps)
  }, POLL_TASK_STATUS_INTERVAL_MS)
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
      } else if (restoration.type === 'resume_status_poll') {
        deps.startStatusPolling(task)
      }
    })
  } catch (error) {
    deps.onParseError?.(error)
  }
}
