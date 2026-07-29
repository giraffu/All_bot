import assert from 'node:assert/strict'
import { test } from 'vitest'

import {
  POLL_TASK_RESULT_MAX_RETRIES,
  POLL_TASK_STATUS_INTERVAL_MS,
  probeDetachedTaskResult,
  pollTaskStatus,
  pollTaskResult,
  reconcileTasksAfterForeground,
  restoreTasksFromStorage,
  serializeTasksForStorage,
  type RuntimeTaskLike
} from './tasksRuntime.ts'

function createTask(overrides: Partial<RuntimeTaskLike> = {}): RuntimeTaskLike {
  return {
    id: 'task-1',
    title: '测试任务',
    progress: 0,
    status: 'pending',
    ...overrides
  }
}

test('restoreTasksFromStorage reloads awaiting-result tasks and resumes result polling instead of status polling', () => {
  const storage = {
    getItem(key: string) {
      assert.equal(key, 'active_tasks')
      return JSON.stringify([
        createTask({
          status: 'running',
          progress: 72,
          awaitingResult: true
        })
      ])
    }
  }

  const activeTasks: RuntimeTaskLike[] = []
  let pollCalls = 0
  let statusPollCalls = 0

  restoreTasksFromStorage(storage, activeTasks, {
    pollForResult: (task) => {
      pollCalls += 1
      assert.equal(task.id, 'task-1')
    },
    startStatusPolling: () => {
      statusPollCalls += 1
    }
  })

  assert.equal(activeTasks.length, 1)
  assert.equal(typeof activeTasks[0].updatedAt, 'number')
  assert.deepEqual({ ...activeTasks[0], updatedAt: undefined }, {
    id: 'task-1',
    title: '测试任务',
    progress: 99,
    status: 'running',
    awaitingResult: true,
    updatedAt: undefined
  })
  assert.equal(pollCalls, 1)
  assert.equal(statusPollCalls, 0)
})

test('restoreTasksFromStorage drops stale pending tasks before attempting status polling', () => {
  const now = 1_700_000_000_000
  const storage = {
    getItem(key: string) {
      assert.equal(key, 'active_tasks')
      return JSON.stringify([
        createTask({
          status: 'pending',
          progress: 10,
          updatedAt: now - (25 * 60 * 60 * 1000)
        })
      ])
    }
  }

  const activeTasks: RuntimeTaskLike[] = []
  let pollCalls = 0
  let statusPollCalls = 0

  restoreTasksFromStorage(storage, activeTasks, {
    pollForResult: () => {
      pollCalls += 1
    },
    startStatusPolling: () => {
      statusPollCalls += 1
    }
  }, now)

  assert.equal(activeTasks.length, 0)
  assert.equal(pollCalls, 0)
  assert.equal(statusPollCalls, 0)
})

test('restoreTasksFromStorage migrates legacy pending tasks without updatedAt into the new ttl tracking', () => {
  const now = 1_700_000_000_000
  const storage = {
    getItem(key: string) {
      assert.equal(key, 'active_tasks')
      return JSON.stringify([
        createTask({
          status: 'pending',
          progress: 10,
          updatedAt: undefined
        })
      ])
    }
  }

  const activeTasks: RuntimeTaskLike[] = []
  let statusPollCalls = 0

  restoreTasksFromStorage(storage, activeTasks, {
    pollForResult: () => {
      throw new Error('legacy pending task should not enter result polling')
    },
    startStatusPolling: (task) => {
      statusPollCalls += 1
      assert.equal(task.updatedAt, now)
    }
  }, now)

  assert.equal(activeTasks.length, 1)
  assert.equal(activeTasks[0].updatedAt, now)
  assert.equal(statusPollCalls, 1)
})

test('restoreTasksFromStorage preserves existing updatedAt when rerouting a restored task to result polling', () => {
  const now = 1_700_000_000_000
  const previousUpdatedAt = now - (2 * 60 * 60 * 1000)
  const storage = {
    getItem(key: string) {
      assert.equal(key, 'active_tasks')
      return JSON.stringify([
        createTask({
          status: 'success',
          progress: 100,
          resultUrl: undefined,
          updatedAt: previousUpdatedAt
        })
      ])
    }
  }

  const activeTasks: RuntimeTaskLike[] = []
  let pollCalls = 0

  restoreTasksFromStorage(storage, activeTasks, {
    pollForResult: (task) => {
      pollCalls += 1
      assert.equal(task.updatedAt, previousUpdatedAt)
      assert.equal(task.awaitingResult, true)
    },
    startStatusPolling: () => {
      throw new Error('success without result url should not resume status polling')
    }
  }, now)

  assert.equal(activeTasks.length, 1)
  assert.equal(activeTasks[0].updatedAt, previousUpdatedAt)
  assert.equal(activeTasks[0].status, 'running')
  assert.equal(activeTasks[0].awaitingResult, true)
  assert.equal(pollCalls, 1)
})

test('reconcileTasksAfterForeground resumes saving and active tasks after a tab is restored', () => {
  const resultTask = createTask({
    id: 'saving-task',
    status: 'running',
    awaitingResult: true,
  })
  const runningTask = createTask({
    id: 'running-task',
    status: 'running',
    awaitingResult: false,
  })
  const completedTask = createTask({
    id: 'completed-task',
    status: 'success',
    resultUrl: 'https://cdn.example/result.png',
  })
  const resultPolls: string[] = []
  const statusPolls: string[] = []

  reconcileTasksAfterForeground(
    [resultTask, runningTask, completedTask],
    {
      pollForResult: task => resultPolls.push(task.id),
      startStatusPolling: task => statusPolls.push(task.id),
    },
  )

  assert.deepEqual(resultPolls, ['saving-task'])
  assert.deepEqual(statusPolls, ['running-task'])
})

test('pollTaskStatus preserves pending type queue position and schedules low-frequency retry', async () => {
  const activeTasks: RuntimeTaskLike[] = [createTask()]
  let scheduledDelay: number | null = null

  await pollTaskStatus(activeTasks[0], activeTasks, {
    apiGet: async (url) => {
      assert.equal(url, '/tasks/task-1/status')
      return { data: { status: 'pending', queue_pos: 2, progress: 42 } }
    },
    schedule: (_callback, delayMs) => {
      scheduledDelay = delayMs
    },
    pollForResult: () => {
      throw new Error('pending task should not poll result')
    },
    finalizeCancelledTask: () => {
      throw new Error('pending task should not finalize cancellation')
    },
    notifyTaskFailure: () => {
      throw new Error('pending task should not fail')
    }
  })

  assert.equal(activeTasks[0].status, 'pending')
  assert.equal(activeTasks[0].queuePos, 2)
  assert.equal(scheduledDelay, POLL_TASK_STATUS_INTERVAL_MS)
})

test('pollTaskStatus clears queue position for running and ignores progress percent', async () => {
  const activeTasks: RuntimeTaskLike[] = [createTask({ queuePos: 1, progress: 0 })]

  await pollTaskStatus(activeTasks[0], activeTasks, {
    apiGet: async () => ({ data: { status: 'running', queue_pos: 1, progress: 87 } }),
    schedule: () => {},
    pollForResult: () => {
      throw new Error('running task should not poll result')
    },
    finalizeCancelledTask: () => {
      throw new Error('running task should not finalize cancellation')
    },
    notifyTaskFailure: () => {
      throw new Error('running task should not fail')
    }
  })

  assert.equal(activeTasks[0].status, 'running')
  assert.equal(activeTasks[0].queuePos, undefined)
  assert.equal(activeTasks[0].progress, 0)
})

test('pollTaskStatus routes success to result polling without opening SSE', async () => {
  const activeTasks: RuntimeTaskLike[] = [createTask({ status: 'running' })]
  let resultPollCalls = 0

  await pollTaskStatus(activeTasks[0], activeTasks, {
    apiGet: async () => ({ data: { status: 'success', progress: 100 } }),
    schedule: () => {
      throw new Error('success should not schedule status retry')
    },
    pollForResult: (task) => {
      resultPollCalls += 1
      assert.equal(task.awaitingResult, true)
    },
    finalizeCancelledTask: () => {
      throw new Error('success task should not finalize cancellation')
    },
    notifyTaskFailure: () => {
      throw new Error('success task should not fail')
    }
  })

  assert.equal(resultPollCalls, 1)
  assert.equal(activeTasks[0].status, 'running')
  assert.equal(activeTasks[0].awaitingResult, true)
  assert.equal(activeTasks[0].progress, 0)
})

test('serializeTasksForStorage preserves per-task updatedAt instead of overwriting every task', () => {
  const now = 1_700_000_000_000
  const serialized = serializeTasksForStorage([
    {
      ...createTask({ id: 'task-1' }),
      updatedAt: now - 60_000,
      eventSource: { close() {} }
    },
    {
      ...createTask({ id: 'task-2' }),
      updatedAt: undefined
    }
  ], now)

  assert.deepEqual(serialized, [
    {
      id: 'task-1',
      title: '测试任务',
      progress: 0,
      status: 'pending',
      updatedAt: now - 60_000
    },
    {
      id: 'task-2',
      title: '测试任务',
      progress: 0,
      status: 'pending',
      updatedAt: now
    }
  ])
})

test('pollTaskResult retries pending_result once and resolves on the next result fetch', async () => {
  const activeTasks: RuntimeTaskLike[] = [
    createTask({
      status: 'running',
      progress: 99,
      awaitingResult: true
    })
  ]

  const responses = [
    { data: { status: 'pending_result' } },
    { data: { status: 'success', result_url: 'https://cdn.example/final.png' } }
  ]

  let apiGetCalls = 0
  let scheduledDelay: number | null = null
  let scheduledCallback: (() => void) | null = null
  let successCalls = 0

  await pollTaskResult(activeTasks[0], activeTasks, {
    apiGet: async (url) => {
      apiGetCalls += 1
      assert.equal(url, '/tasks/task-1/result')
      const next = responses.shift()
      assert.ok(next)
      return next
    },
    schedule: (callback, delayMs) => {
      scheduledDelay = delayMs
      scheduledCallback = callback
    },
    onSuccess: (task) => {
      successCalls += 1
      assert.equal(task.resultUrl, 'https://cdn.example/final.png')
    }
  })

  assert.equal(apiGetCalls, 1)
  assert.equal(scheduledDelay, 1500)
  assert.equal(activeTasks[0].status, 'running')
  assert.equal(activeTasks[0].awaitingResult, true)

  if (!scheduledCallback) {
    throw new Error('expected retry to be scheduled')
  }
  ;(scheduledCallback as () => void)()
  await Promise.resolve()

  assert.equal(apiGetCalls, 2)
  assert.equal(successCalls, 1)
  assert.equal(typeof activeTasks[0].updatedAt, 'number')
  assert.deepEqual({ ...activeTasks[0], updatedAt: undefined }, {
    id: 'task-1',
    title: '测试任务',
    progress: 100,
    status: 'success',
    awaitingResult: false,
    resultUrl: 'https://cdn.example/final.png',
    extraOutputs: {},
    resultMeta: {},
    error: undefined,
    updatedAt: undefined
  })
})

test('pollTaskResult keeps waiting beyond the old short result window', async () => {
  const activeTasks: RuntimeTaskLike[] = [
    createTask({
      status: 'running',
      progress: 99,
      awaitingResult: true
    })
  ]

  let scheduledDelay: number | null = null
  let timeoutCalls = 0

  await pollTaskResult(activeTasks[0], activeTasks, {
    apiGet: async () => ({ data: { status: 'pending_result' } }),
    schedule: (_callback, delayMs) => {
      scheduledDelay = delayMs
    },
    onTimeout: () => {
      timeoutCalls += 1
    }
  }, 10)

  assert.equal(timeoutCalls, 0)
  assert.equal(scheduledDelay, 1500)
  assert.equal(activeTasks[0].status, 'running')
  assert.equal(activeTasks[0].awaitingResult, true)
  assert.ok(POLL_TASK_RESULT_MAX_RETRIES > 10)
})

test('probeDetachedTaskResult keeps the floating task pending until history result becomes available', async () => {
  const activeTasks: RuntimeTaskLike[] = [
    createTask({
      status: 'pending',
      progress: 0
    })
  ]

  const responses = [
    { data: { status: 'pending_result' } },
    { data: { status: 'success', result_url: 'https://cdn.example/detached.png' } }
  ]

  let apiGetCalls = 0
  let scheduledDelay: number | null = null
  let scheduledCallback: (() => void) | null = null
  let resolvedCalls = 0

  await probeDetachedTaskResult(activeTasks[0], activeTasks, {
    apiGet: async (url) => {
      apiGetCalls += 1
      assert.equal(url, '/tasks/task-1/result')
      const next = responses.shift()
      assert.ok(next)
      return next
    },
    schedule: (callback, delayMs) => {
      scheduledDelay = delayMs
      scheduledCallback = callback
    },
    onResolved: (task) => {
      resolvedCalls += 1
      assert.equal(task.resultUrl, 'https://cdn.example/detached.png')
    }
  }, 0, 3, 5000)

  assert.equal(apiGetCalls, 1)
  assert.equal(scheduledDelay, 5000)
  assert.equal(activeTasks[0].status, 'pending')
  assert.equal(activeTasks[0].resultUrl, undefined)

  if (!scheduledCallback) {
    throw new Error('expected detached probe retry to be scheduled')
  }
  ;(scheduledCallback as () => void)()
  await Promise.resolve()

  assert.equal(apiGetCalls, 2)
  assert.equal(resolvedCalls, 1)
  assert.deepEqual({ ...activeTasks[0], updatedAt: undefined }, {
    id: 'task-1',
    title: '测试任务',
    progress: 100,
    status: 'success',
    awaitingResult: false,
    resultUrl: 'https://cdn.example/detached.png',
    extraOutputs: {},
    resultMeta: {},
    error: undefined,
    updatedAt: undefined
  })
})

test('probeDetachedTaskResult marks the floating task failed on forbidden result lookup', async () => {
  const activeTasks: RuntimeTaskLike[] = [
    createTask({
      status: 'running',
      progress: 42
    })
  ]

  let forbiddenCalls = 0

  await probeDetachedTaskResult(activeTasks[0], activeTasks, {
    apiGet: async () => {
      throw { response: { status: 403 } }
    },
    schedule: () => {
      throw new Error('forbidden lookup should not schedule detached retries')
    },
    onForbidden: (task) => {
      forbiddenCalls += 1
      assert.equal(task.error, '任务不存在或无权限')
    }
  })

  assert.equal(forbiddenCalls, 1)
  assert.deepEqual({ ...activeTasks[0], updatedAt: undefined }, {
    id: 'task-1',
    title: '测试任务',
    progress: 42,
    status: 'failed',
    awaitingResult: false,
    error: '任务不存在或无权限',
    updatedAt: undefined
  })
})
