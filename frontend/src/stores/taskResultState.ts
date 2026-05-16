export interface TaskResultResponsePayload {
  status?: string
  result_url?: string | null
}

export interface TaskResultDecision {
  type: 'resolved' | 'retry' | 'timeout' | 'forbidden'
  resultUrl?: string
}

export interface ResumableTaskLike {
  status: 'pending' | 'running' | 'success' | 'failed'
  resultUrl?: string
}

export interface RecoverableTaskLike extends ResumableTaskLike {
  progress: number
  awaitingResult?: boolean
  error?: string
}

export interface TaskRestoreDecision<T extends RecoverableTaskLike> {
  type: 'poll_result' | 'resume_sse' | 'idle'
  task: T
}

export interface TaskResultTransition<T extends RecoverableTaskLike> {
  type: 'resolved' | 'retry' | 'timeout' | 'forbidden'
  task: T
  nextRetryCount?: number
}

export function decideTaskResultFromResponse(
  payload: TaskResultResponsePayload,
  retryCount: number,
  maxRetries: number
): TaskResultDecision {
  if (payload.status === 'success' && payload.result_url) {
    return { type: 'resolved', resultUrl: payload.result_url }
  }

  if (payload.status === 'pending_result' && retryCount < maxRetries) {
    return { type: 'retry' }
  }

  return { type: 'timeout' }
}

export function decideTaskResultFromError(
  status: number | undefined,
  retryCount: number,
  maxRetries: number
): TaskResultDecision {
  if (status === 403) {
    return { type: 'forbidden' }
  }

  if (retryCount < maxRetries) {
    return { type: 'retry' }
  }

  return { type: 'timeout' }
}

export function shouldResumeTaskListening(task: ResumableTaskLike): boolean {
  return task.status === 'pending' || task.status === 'running'
}

export function restorePersistedTask<T extends RecoverableTaskLike>(
  task: T
): TaskRestoreDecision<T> {
  if (task.awaitingResult || (task.status === 'success' && !task.resultUrl)) {
    return {
      type: 'poll_result',
      task: {
        ...task,
        awaitingResult: true,
        status: 'running',
        progress: Math.max(task.progress, 99)
      }
    }
  }

  if (shouldResumeTaskListening(task)) {
    return {
      type: 'resume_sse',
      task
    }
  }

  return {
    type: 'idle',
    task
  }
}

export function applyTaskResultResponseToTask<T extends RecoverableTaskLike>(
  task: T,
  payload: TaskResultResponsePayload,
  retryCount: number,
  maxRetries: number
): TaskResultTransition<T> {
  const decision = decideTaskResultFromResponse(payload, retryCount, maxRetries)

  if (decision.type === 'resolved' && decision.resultUrl) {
    return {
      type: 'resolved',
      task: {
        ...task,
        progress: 100,
        status: 'success',
        resultUrl: decision.resultUrl,
        awaitingResult: false,
        error: undefined
      }
    }
  }

  if (decision.type === 'retry') {
    return {
      type: 'retry',
      task: {
        ...task,
        status: 'running',
        progress: Math.max(task.progress, 99),
        awaitingResult: true
      },
      nextRetryCount: retryCount + 1
    }
  }

  return {
    type: 'timeout',
    task: {
      ...task,
      status: 'failed',
      error: '获取结果超时，请在历史记录中查看',
      awaitingResult: false
    }
  }
}

export function applyTaskResultErrorToTask<T extends RecoverableTaskLike>(
  task: T,
  status: number | undefined,
  retryCount: number,
  maxRetries: number
): TaskResultTransition<T> {
  const decision = decideTaskResultFromError(status, retryCount, maxRetries)

  if (decision.type === 'forbidden') {
    return {
      type: 'forbidden',
      task: {
        ...task,
        status: 'failed',
        error: '任务不存在或无权限',
        awaitingResult: false
      }
    }
  }

  if (decision.type === 'retry') {
    return {
      type: 'retry',
      task: {
        ...task,
        status: 'running',
        progress: Math.max(task.progress, 99),
        awaitingResult: true
      },
      nextRetryCount: retryCount + 1
    }
  }

  return {
    type: 'timeout',
    task: {
      ...task,
      status: 'failed',
      error: '获取结果失败',
      awaitingResult: false
    }
  }
}
