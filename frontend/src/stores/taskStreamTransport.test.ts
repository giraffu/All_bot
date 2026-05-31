import { describe, expect, it, vi } from 'vitest'

import type { Task } from './taskStoreTypes'
import { handleTaskProgressPayload } from './taskStreamTransport'

const createTask = (overrides: Partial<Task> = {}): Task => ({
  id: 'task-1',
  type: 'wan22_video_v2',
  title: '图生视频 v2',
  progress: 0,
  status: 'pending',
  ...overrides,
})

describe('handleTaskProgressPayload', () => {
  it('keeps pending status and queue position visible for pending payloads with progress', () => {
    const task = createTask()

    handleTaskProgressPayload(
      task,
      {
        status: 'pending',
        progress: 0,
        queue_pos: 2,
      },
      {
        pollForResult: vi.fn(),
        finalizeCancelledTask: vi.fn(),
        closeTaskStream: vi.fn(),
        notifyTaskFailure: vi.fn(),
      },
    )

    expect(task.status).toBe('pending')
    expect(task.progress).toBe(0)
    expect(task.queuePos).toBe(2)
  })

  it('switches to running and clears queue position once execution starts', () => {
    const task = createTask({ queuePos: 1 })

    handleTaskProgressPayload(
      task,
      {
        status: 'running',
        progress: 12,
      },
      {
        pollForResult: vi.fn(),
        finalizeCancelledTask: vi.fn(),
        closeTaskStream: vi.fn(),
        notifyTaskFailure: vi.fn(),
      },
    )

    expect(task.status).toBe('running')
    expect(task.progress).toBe(12)
    expect(task.queuePos).toBeUndefined()
  })
})
