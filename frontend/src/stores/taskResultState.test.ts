import assert from 'node:assert/strict'
import { test } from 'vitest'

import {
  applyTaskResultResponseToTask,
  decideTaskResultFromError,
  decideTaskResultFromResponse,
  restorePersistedTask,
  shouldResumeTaskListening
} from './taskResultState.ts'

test('decideTaskResultFromResponse retries while result is still pending', () => {
  const decision = decideTaskResultFromResponse(
    { status: 'pending_result' },
    2,
    10
  )

  assert.deepEqual(decision, { type: 'retry' })
})

test('decideTaskResultFromResponse resolves when result url becomes available', () => {
  const decision = decideTaskResultFromResponse(
    { status: 'success', result_url: 'https://cdn.example/result.png' },
    3,
    10
  )

  assert.deepEqual(decision, {
    type: 'resolved',
    resultUrl: 'https://cdn.example/result.png',
    extraOutputs: {}
  })
})

test('decideTaskResultFromError keeps retrying transient not-ready responses', () => {
  const decision = decideTaskResultFromError(404, 4, 10)

  assert.deepEqual(decision, { type: 'retry' })
})

test('shouldResumeTaskListening only resumes pending or running tasks', () => {
  assert.equal(
    shouldResumeTaskListening({
      status: 'pending',
      resultUrl: undefined
    }),
    true
  )

  assert.equal(
    shouldResumeTaskListening({
      status: 'running',
      resultUrl: undefined
    }),
    true
  )

  assert.equal(
    shouldResumeTaskListening({
      status: 'success',
      resultUrl: undefined
    }),
    false
  )
})

test('restorePersistedTask routes success without result url to result polling before SSE restore checks', () => {
  const restoration = restorePersistedTask({
    status: 'success',
    progress: 100,
    awaitingResult: false,
    resultUrl: undefined
  })

  assert.equal(restoration.type, 'poll_result')
  assert.deepEqual(restoration.task, {
    status: 'running',
    progress: 100,
    awaitingResult: true,
    resultUrl: undefined
  })
})

test('restorePersistedTask keeps awaiting-result tasks in running state and resumes result polling', () => {
  const restoration = restorePersistedTask({
    status: 'running',
    progress: 72,
    awaitingResult: true,
    resultUrl: undefined
  })

  assert.equal(restoration.type, 'poll_result')
  assert.deepEqual(restoration.task, {
    status: 'running',
    progress: 99,
    awaitingResult: true,
    resultUrl: undefined
  })
})

test('applyTaskResultResponseToTask transitions from pending_result retries to success once result arrives', () => {
  const task = {
    status: 'running' as const,
    progress: 99,
    awaitingResult: true,
    resultUrl: undefined
  }

  const retryTransition = applyTaskResultResponseToTask(
    task,
    { status: 'pending_result' },
    0,
    10
  )

  assert.equal(retryTransition.type, 'retry')
  assert.equal(retryTransition.nextRetryCount, 1)
  assert.deepEqual(retryTransition.task, {
    status: 'running',
    progress: 99,
    awaitingResult: true,
    resultUrl: undefined
  })

  const successTransition = applyTaskResultResponseToTask(
    retryTransition.task,
    { status: 'success', result_url: 'https://cdn.example/final.png' },
    retryTransition.nextRetryCount ?? 1,
    10
  )

  assert.equal(successTransition.type, 'resolved')
  assert.deepEqual(successTransition.task, {
    status: 'success',
    progress: 100,
    awaitingResult: false,
    resultUrl: 'https://cdn.example/final.png',
    extraOutputs: {},
    error: undefined
  })
})
