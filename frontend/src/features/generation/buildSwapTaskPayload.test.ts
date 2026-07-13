import { describe, expect, it } from 'vitest'

import { buildSwapTaskPayload } from './buildSwapTaskPayload'

describe('buildSwapTaskPayload', () => {
  it('builds face swap payload with template metadata', () => {
    expect(
      buildSwapTaskPayload({
        taskType: 'face_swap',
        faceImage: 'uploads/face.png',
        targetField: 'target_image',
        targetAsset: 'uploads/target.png',
        isTemplate: true,
        sourcePostId: 88,
      }),
    ).toEqual({
      task_type: 'face_swap',
      inputs: {
        face_image: 'uploads/face.png',
        target_image: 'uploads/target.png',
      },
      priority: 0,
      is_template: true,
      source_post_id: 88,
    })
  })

  it('builds face video payload with resolution override', () => {
    expect(
      buildSwapTaskPayload({
        taskType: 'face_video',
        faceImage: 'uploads/face.png',
        targetField: 'target_video',
        targetAsset: 'uploads/target.mp4',
        resolution: 1024,
      }),
    ).toEqual({
      task_type: 'face_video',
      inputs: {
        face_image: 'uploads/face.png',
        target_video: 'uploads/target.mp4',
        resolution: 1024,
      },
      priority: 0,
      is_template: false,
    })
  })
})
