import assert from 'node:assert/strict'
import { test } from 'vitest'

import {
  pollTaskResult,
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

test('restoreTasksFromStorage reloads awaiting-result tasks and resumes result polling instead of SSE', () => {
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
  let sseCalls = 0

  restoreTasksFromStorage(storage, activeTasks, {
    pollForResult: (task) => {
      pollCalls += 1
      assert.equal(task.id, 'task-1')
    },
    startListening: () => {
      sseCalls += 1
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
  assert.equal(sseCalls, 0)
})

test('restoreTasksFromStorage drops stale pending tasks before attempting SSE resume', () => {
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
  let sseCalls = 0

  restoreTasksFromStorage(storage, activeTasks, {
    pollForResult: () => {
      pollCalls += 1
    },
    startListening: () => {
      sseCalls += 1
    }
  }, now)

  assert.equal(activeTasks.length, 0)
  assert.equal(pollCalls, 0)
  assert.equal(sseCalls, 0)
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
  let sseCalls = 0

  restoreTasksFromStorage(storage, activeTasks, {
    pollForResult: () => {
      throw new Error('legacy pending task should not enter result polling')
    },
    startListening: (task) => {
      sseCalls += 1
      assert.equal(task.updatedAt, now)
    }
  }, now)

  assert.equal(activeTasks.length, 1)
  assert.equal(activeTasks[0].updatedAt, now)
  assert.equal(sseCalls, 1)
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
    startListening: () => {
      throw new Error('success without result url should not resume SSE')
    }
  }, now)

  assert.equal(activeTasks.length, 1)
  assert.equal(activeTasks[0].updatedAt, previousUpdatedAt)
  assert.equal(activeTasks[0].status, 'running')
  assert.equal(activeTasks[0].awaitingResult, true)
  assert.equal(pollCalls, 1)
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
    error: undefined,
    updatedAt: undefined
  })
})
