import { describe, expect, it } from 'vitest'

import { useGenerationRouteConfig } from './generationRouteConfig'

describe('generationRouteConfig', () => {
  it('falls back to route defaults when a disabled web task type is provided', () => {
    const route = {
      query: {
        type: 'i2i_draw',
        title: '局部重绘',
        cost: '3',
      },
      meta: {
        generation: {
          taskType: 'i2i_pro',
          title: '图片生成',
          cost: 6,
        },
      },
    } as any

    const config = useGenerationRouteConfig(route, {
      taskType: 'edit',
      title: '默认',
      cost: 2,
    })

    expect(config.taskType.value).toBe('i2i_pro')
    expect(config.taskTitle.value).toBe('图片生成')
    expect(config.taskCost.value).toBe(6)
  })
})
