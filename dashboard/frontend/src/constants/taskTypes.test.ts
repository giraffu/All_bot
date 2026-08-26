import { describe, expect, it } from 'vitest'

import { TASK_TYPE_LABELS, TASK_TYPE_OPTIONS } from './taskTypes'

describe('dashboard history task types', () => {
  it('groups MiniMax H3 history into image and reference image video filters', () => {
    const h3Options = TASK_TYPE_OPTIONS.filter(option =>
      option.label.startsWith('高级图生视频pro'),
    )

    expect(h3Options).toEqual([
      {
        label: '高级图生视频pro · 图生视频',
        value: 'minimax_h3_t2v,minimax_h3_i2v,minimax_h3_flf2v',
      },
      {
        label: '高级图生视频pro · 参考图生视频',
        value: 'minimax_h3_ref2v',
      },
    ])
  })

  it('keeps the concrete H3 mode visible on each history row', () => {
    expect(TASK_TYPE_LABELS).toMatchObject({
      minimax_h3_t2v: '高级图生视频pro · 文生视频',
      minimax_h3_i2v: '高级图生视频pro · 图生视频',
      minimax_h3_flf2v: '高级图生视频pro · 首尾帧视频',
      minimax_h3_ref2v: '高级图生视频pro · 参考图生视频',
    })
  })
})
