import { describe, expect, it } from 'vitest'

import {
  buildCreditConsumptionPieData,
  buildGpuEfficiencyPieData,
} from './taskAnalyticsCharts'

describe('task analytics chart transforms', () => {
  it('builds generation credit slices from the daily ledger response', () => {
    expect(buildCreditConsumptionPieData({
      values: {
        minimax_h3_i2v: 120,
        txt2img: 8,
      },
    })).toEqual([
      expect.objectContaining({
        taskType: 'minimax_h3_i2v',
        name: '高级图生视频pro · 图生视频',
        value: 120,
      }),
      expect.objectContaining({
        taskType: 'txt2img',
        name: '文生图',
        value: 8,
      }),
    ])
  })

  it('keeps efficiency evidence on each pie slice for the tooltip', () => {
    const result = buildGpuEfficiencyPieData({
      items: {
        minimax_h3_ref2v: {
          value: 742.5,
          credits: 330,
          gpu_hours: 0.4444,
          task_count: 12,
          estimated: true,
        },
      },
    })

    expect(result).toEqual([
      expect.objectContaining({
        taskType: 'minimax_h3_ref2v',
        name: '高级图生视频pro · 参考图生视频',
        value: 742.5,
        credits: 330,
        gpuHours: 0.4444,
        taskCount: 12,
        estimated: true,
      }),
    ])
  })
})
