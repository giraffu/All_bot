import { describe, expect, it } from 'vitest'

import {
  createPendingTask,
  settleExternalTaskSession,
} from './taskSessionState'

describe('external task session settlement', () => {
  it('turns a pending character-view task into a clean successful terminal task', () => {
    const task = createPendingTask('character-view-task', 'free_edit_v2_5', '人物参考图')
    task.queuePos = 2
    task.error = '任务不存在或无权限'
    task.awaitingResult = true

    settleExternalTaskSession(task, {
      status: 'success',
      resultUrl: 'https://example.com/view.png',
    })

    expect(task).toMatchObject({
      status: 'success',
      progress: 100,
      resultUrl: 'https://example.com/view.png',
      awaitingResult: false,
    })
    expect(task.queuePos).toBeUndefined()
    expect(task.error).toBeUndefined()
  })

  it('keeps a real character-view failure as a failed terminal task', () => {
    const task = createPendingTask('character-view-task', 'free_edit_v2_5', '人物参考图')

    settleExternalTaskSession(task, {
      status: 'failed',
      error: '人物子图生成失败',
    })

    expect(task).toMatchObject({
      status: 'failed',
      progress: 0,
      error: '人物子图生成失败',
      awaitingResult: false,
    })
  })
})
