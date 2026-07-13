import assert from 'node:assert/strict'
import { test } from 'vitest'

import {
  countBlockingFloatingTasks,
  getOldestTerminalFloatingTaskIdsForNewTask,
  MAX_FLOATING_TASKS,
} from './taskFloatingSlots'

test('countBlockingFloatingTasks ignores completed bubbles', () => {
  assert.equal(countBlockingFloatingTasks([
    { status: 'pending' },
    { status: 'running' },
    { status: 'success' },
    { status: 'failed' },
    { status: 'cancelled' },
  ]), 2)
})

test('getOldestTerminalFloatingTaskIdsForNewTask evicts the oldest completed bubble first', () => {
  assert.deepEqual(
    getOldestTerminalFloatingTaskIdsForNewTask([
      { id: 'done-newer', status: 'success', updatedAt: 300 },
      { id: 'running', status: 'running', updatedAt: 200 },
      { id: 'done-oldest', status: 'failed', updatedAt: 100 },
    ]),
    ['done-oldest']
  )
})

test('getOldestTerminalFloatingTaskIdsForNewTask requests multiple evictions when storage is already over limit', () => {
  assert.deepEqual(
    getOldestTerminalFloatingTaskIdsForNewTask([
      { id: 'done-1', status: 'success', updatedAt: 100 },
      { id: 'done-2', status: 'cancelled', updatedAt: 200 },
      { id: 'done-3', status: 'failed', updatedAt: 300 },
      { id: 'running', status: 'running', updatedAt: 400 },
    ], MAX_FLOATING_TASKS),
    ['done-1', 'done-2']
  )
})
