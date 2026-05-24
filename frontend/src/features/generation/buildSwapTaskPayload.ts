import type { GenerationTaskPayload } from './buildGenerationTaskPayload'

export type SwapTargetField = 'target_image' | 'target_video'

export type BuildSwapTaskPayloadOptions = {
  taskType: 'face_swap' | 'face_video'
  faceImage: string
  targetField: SwapTargetField
  targetAsset: string
  resolution?: number
  priority?: number
  isTemplate?: boolean
  sourcePostId?: number | null
}

export function buildSwapTaskPayload(
  options: BuildSwapTaskPayloadOptions,
): GenerationTaskPayload {
  const {
    taskType,
    faceImage,
    targetField,
    targetAsset,
    resolution,
    priority = 0,
    isTemplate = false,
    sourcePostId,
  } = options

  const payload: GenerationTaskPayload = {
    task_type: taskType,
    inputs: {
      face_image: faceImage,
      [targetField]: targetAsset,
    },
    priority,
    is_template: isTemplate,
  }

  if (resolution !== undefined) {
    payload.inputs.resolution = resolution
  }

  if (sourcePostId != null) {
    payload.source_post_id = sourcePostId
  }

  return payload
}
