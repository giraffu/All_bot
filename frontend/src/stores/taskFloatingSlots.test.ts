import assert from 'node:assert/strict'
import { test } from 'vitest'

import {
  COMPACT_FLOATING_TASK_SLOTS,
  getOldestTerminalFloatingTaskIdsForNewTask,
} from './taskFloatingSlots'

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
    ], COMPACT_FLOATING_TASK_SLOTS),
    ['done-1', 'done-2']
  )
})

test('getOldestTerminalFloatingTaskIdsForNewTask never evicts active tasks above the compact slot count', () => {
  assert.deepEqual(
    getOldestTerminalFloatingTaskIdsForNewTask([
      { id: 'pending-1', status: 'pending' },
      { id: 'running-2', status: 'running' },
      { id: 'pending-3', status: 'pending' },
      { id: 'running-4', status: 'running' },
    ]),
    []
  )
})
