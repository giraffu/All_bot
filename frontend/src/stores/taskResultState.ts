import type { TaskExtraOutputs, Wan22ResultMeta } from '@/types/gallery'

export interface TaskResultResponsePayload {
  status?: string
  result_url?: string | null
  result_kind?: 'media' | 'text' | string | null
  result_text?: string | null
  partial_result_text?: string | null
  refund_status?: string | null
  message?: string | null
  extra_outputs?: TaskExtraOutputs | null
  result_meta?: (Wan22ResultMeta & Record<string, unknown>) | Record<string, unknown> | null
}

export interface TaskResultDecision {
  type: 'resolved' | 'retry' | 'timeout' | 'forbidden'
  resultUrl?: string
  resultKind?: 'media' | 'text'
  resultText?: string
  extraOutputs?: TaskExtraOutputs
  resultMeta?: Wan22ResultMeta
}

export interface ResumableTaskLike {
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
  resultUrl?: string
  resultKind?: 'media' | 'text'
  resultText?: string
  extraOutputs?: TaskExtraOutputs
  resultMeta?: Wan22ResultMeta
}

export interface RecoverableTaskLike extends ResumableTaskLike {
  progress: number
  awaitingResult?: boolean
  error?: string
}

export interface TaskRestoreDecision<T extends RecoverableTaskLike> {
  type: 'poll_result' | 'resume_status_poll' | 'idle'
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
    return {
      type: 'resolved',
      resultUrl: payload.result_url,
      extraOutputs: payload.extra_outputs ?? {},
      resultMeta: payload.result_meta ?? {}
    }
  }

  if (
    payload.status === 'success'
    && payload.result_kind === 'text'
    && String(payload.result_text || '').trim()
  ) {
    return {
      type: 'resolved',
      resultKind: 'text',
      resultText: String(payload.result_text).trim(),
      extraOutputs: payload.extra_outputs ?? {},
      resultMeta: payload.result_meta ?? {}
    }
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

export function shouldResumeTaskStatusPolling(task: ResumableTaskLike): boolean {
  return task.status === 'pending' || task.status === 'running'
}

export function restorePersistedTask<T extends RecoverableTaskLike>(
  task: T
): TaskRestoreDecision<T> {
  const hasTerminalResult = Boolean(task.resultUrl)
    || (task.resultKind === 'text' && Boolean(task.resultText))
  if (task.awaitingResult || (task.status === 'success' && !hasTerminalResult)) {
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

  if (shouldResumeTaskStatusPolling(task)) {
    return {
      type: 'resume_status_poll',
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

  if (decision.type === 'resolved' && (decision.resultUrl || decision.resultText)) {
    return {
      type: 'resolved',
      task: {
        ...task,
        progress: 100,
        status: 'success',
        resultUrl: decision.resultUrl,
        ...(decision.resultKind ? { resultKind: decision.resultKind } : {}),
        ...(decision.resultText ? { resultText: decision.resultText } : {}),
        extraOutputs: decision.extraOutputs ?? {},
        resultMeta: decision.resultMeta ?? {},
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
