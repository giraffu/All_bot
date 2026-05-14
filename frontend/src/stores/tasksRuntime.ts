import {
  applyTaskResultErrorToTask,
  applyTaskResultResponseToTask,
  restorePersistedTask
} from './taskResultState.ts'

export interface RuntimeTaskLike {
  id: string
  title: string
  progress: number
  status: 'pending' | 'running' | 'success' | 'failed'
  resultUrl?: string
  error?: string
  awaitingResult?: boolean
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

export interface RestoreTasksDeps<T extends RuntimeTaskLike> {
  startListening: (task: T) => void
  pollForResult: (task: T) => void
  onParseError?: (error: unknown) => void
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
    Object.assign(currentTask, transition.task)

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
    Object.assign(currentTask, transition.task)

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

export function restoreTasksFromStorage<T extends RuntimeTaskLike>(
  storage: RuntimeStorageLike,
  activeTasks: T[],
  deps: RestoreTasksDeps<T>
): void {
  const storedTasks = storage.getItem('active_tasks')
  if (!storedTasks) return

  try {
    const parsed = JSON.parse(storedTasks) as T[]
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
