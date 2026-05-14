import test from 'node:test'
import assert from 'node:assert/strict'

import {
  pollTaskResult,
  restoreTasksFromStorage,
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
  assert.deepEqual(activeTasks[0], {
    id: 'task-1',
    title: '测试任务',
    progress: 99,
    status: 'running',
    awaitingResult: true
  })
  assert.equal(pollCalls, 1)
  assert.equal(sseCalls, 0)
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
  assert.deepEqual(activeTasks[0], {
    id: 'task-1',
    title: '测试任务',
    progress: 100,
    status: 'success',
    awaitingResult: false,
    resultUrl: 'https://cdn.example/final.png',
    error: undefined
  })
})
