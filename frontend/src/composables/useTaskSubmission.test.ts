import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  addTask: vi.fn(),
  post: vi.fn(),
  success: vi.fn(),
  updateBalance: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('@/api', () => ({
  default: { post: mocks.post },
}))

vi.mock('ant-design-vue', () => ({
  message: {
    success: mocks.success,
    warning: mocks.warning,
  },
}))

vi.mock('@/stores/tasks', () => ({
  useTasksStore: () => ({
    addTask: mocks.addTask,
  }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ updateBalance: mocks.updateBalance }),
}))

import { useTaskSubmission } from './useTaskSubmission'

describe('useTaskSubmission', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.post.mockResolvedValue({
      data: { task_id: 'task-4', balance_remaining: 88 },
    })
  })

  it('lets the backend decide concurrency and tracks a fourth active task', async () => {
    const { submitTask } = useTaskSubmission()

    await expect(
      submitTask({ task_type: 'img2video' }, '第四个任务')
    ).resolves.toBe('task-4')

    expect(mocks.post).toHaveBeenCalledWith('/tasks/generate', {
      task_type: 'img2video',
    })
    expect(mocks.addTask).toHaveBeenCalledWith(
      'task-4',
      'img2video',
      '第四个任务',
    )
    expect(mocks.warning).not.toHaveBeenCalled()
  })
})
