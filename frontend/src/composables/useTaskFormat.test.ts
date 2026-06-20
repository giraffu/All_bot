import { describe, expect, it } from 'vitest'

import { useTaskFormat } from './useTaskFormat'

describe('useTaskFormat', () => {
  it('labels current video and text task aliases', () => {
    const { getTypeLabel } = useTaskFormat()

    expect(getTypeLabel('scail2_video_replacement')).toBe('视频换人')
    expect(getTypeLabel('scail2_action_transfer')).toBe('动作迁移')
    expect(getTypeLabel('scail2_face_swap_v2')).toBe('视频换脸')
    expect(getTypeLabel('video_insert')).toBe('图生视频')
    expect(getTypeLabel('image_to_video')).toBe('图生视频')
    expect(getTypeLabel('t2i-pornmaster-turbo')).toBe('文生图')
  })
})
