import type { Task, TaskProgressPayload } from './taskStoreTypes'
import { touchTaskActivity } from './tasksRuntime'

export interface TaskProgressMessageDeps {
  pollForResult: (task: Task) => void
  finalizeCancelledTask: (task: Task, cancelMessage?: string) => void
  closeTaskStream: (task: Task) => void
  notifyTaskFailure: (task: Task) => void
}

export interface StartTaskStreamListeningDeps {
  apiBaseURL: string
  getToken: () => string | null
  fetchImpl?: typeof fetch
  handleTaskProgressPayload: (task: Task, payload: TaskProgressPayload) => void
  closeTaskStream: (task: Task) => void
  touchTask: (task: Task) => void
  handleUnauthorized: () => void
  scheduleRetry: (taskId: string, retryCount: number) => void
  handleRetryExhausted: (task: Task) => void
}

export function buildTaskStreamUrl(apiBaseURL: string, taskId: string): string {
  const normalizedBaseURL = String(apiBaseURL || '/api').replace(/\/$/, '')
  return `${normalizedBaseURL}/tasks/${taskId}/stream`
}

export function closeTaskStream(task: Task): void {
  if (!task.eventSource) {
    return
  }
  task.eventSource.close()
  task.eventSource = undefined
}

export function handleTaskProgressPayload(
  task: Task,
  payload: TaskProgressPayload,
  deps: TaskProgressMessageDeps,
): void {
  if (payload.status === 'pending' && payload.queue_pos != null) {
    task.queuePos = payload.queue_pos
    touchTaskActivity(task)
  }

  if (payload.progress !== undefined) {
    task.progress = payload.progress
    if (task.status !== 'cancelled' && payload.status === 'running') {
      task.status = 'running'
      task.queuePos = undefined
    } else if (task.status !== 'cancelled' && payload.status === 'pending') {
      task.status = 'pending'
    }
    touchTaskActivity(task)
  }

  if (payload.status === 'success') {
    task.progress = 99
    task.cancelRequested = false
    task.refundStatus = undefined
    task.refundMessage = undefined
    task.awaitingResult = true
    touchTaskActivity(task)
    deps.closeTaskStream(task)
    deps.pollForResult(task)
    return
  }

  if (
    payload.status === 'cancelled'
    || (payload.status === 'failed' && task.cancelRequested && String(payload.error || '').includes('取消'))
  ) {
    task.cancelMessage = payload.message || payload.error || '任务已取消'
    deps.finalizeCancelledTask(task, task.cancelMessage)
    return
  }

  if (payload.status === 'failed') {
    task.status = 'failed'
    task.cancelRequested = false
    task.refundStatus = undefined
    task.refundMessage = undefined
    task.error = payload.error || '未知错误'
    touchTaskActivity(task)
    deps.notifyTaskFailure(task)
    deps.closeTaskStream(task)
  }
}

export function startTaskStreamListening(
  task: Task,
  deps: StartTaskStreamListeningDeps,
): void {
  deps.closeTaskStream(task)

  const token = deps.getToken()
  if (!token) {
    deps.handleUnauthorized()
    return
  }

  const controller = new AbortController()
  const streamHandle = {
    close: () => controller.abort(),
  }
  task.eventSource = streamHandle
  deps.touchTask(task)

  const consumeStream = async () => {
    try {
      const response = await (deps.fetchImpl ?? fetch)(
        buildTaskStreamUrl(deps.apiBaseURL, task.id),
        {
          method: 'GET',
          headers: {
            Accept: 'text/event-stream',
            Authorization: `Bearer ${token}`,
          },
          signal: controller.signal,
          credentials: 'same-origin',
        },
      )

      if (!response.ok) {
        const error: Error & { status?: number } = new Error(`SSE request failed: ${response.status}`)
        error.status = response.status
        throw error
      }

      if (!response.body) {
        throw new Error('SSE response body is empty')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      const processChunk = (chunk: string) => {
        const normalizedChunk = chunk.trim()
        if (!normalizedChunk) {
          return
        }

        let eventName = 'message'
        const dataLines: string[] = []
        normalizedChunk.split('\n').forEach((line) => {
          if (line.startsWith('event:')) {
            eventName = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            dataLines.push(line.slice(5).trimStart())
          }
        })

        if (eventName !== 'progress') {
          return
        }

        const eventData = dataLines.join('\n')
        if (!eventData) {
          return
        }

        try {
          deps.handleTaskProgressPayload(task, JSON.parse(eventData))
        } catch (parseError) {
          console.warn('Skipping malformed SSE payload', parseError, eventData)
        }
      }

      while (true) {
        const { value, done } = await reader.read()
        if (done) {
          break
        }

        buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r/g, '')
        let boundaryIndex = buffer.indexOf('\n\n')
        while (boundaryIndex !== -1) {
          const chunk = buffer.slice(0, boundaryIndex)
          buffer = buffer.slice(boundaryIndex + 2)
          processChunk(chunk)
          boundaryIndex = buffer.indexOf('\n\n')
        }
      }

      if (buffer) {
        processChunk(buffer)
      }

      if (
        task.eventSource === streamHandle
        && !controller.signal.aborted
        && (task.status === 'pending' || task.status === 'running')
      ) {
        throw new Error('SSE connection closed unexpectedly')
      }
    } catch (error) {
      if (controller.signal.aborted) {
        return
      }

      console.error('Failed to parse SSE data', error)
      deps.closeTaskStream(task)

      if ((error as { status?: number })?.status === 401) {
        deps.handleUnauthorized()
        return
      }

      const nextRetryCount = (task.retryCount ?? 0) + 1
      task.retryCount = nextRetryCount
      deps.touchTask(task)

      if (nextRetryCount <= 3) {
        deps.scheduleRetry(task.id, nextRetryCount)
        return
      }

      deps.handleRetryExhausted(task)
    }
  }

  void consumeStream()
}
