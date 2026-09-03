import {
  DEFAULT_FACE_VIDEO_RESOLUTION,
  DEFAULT_LTX_VIDEO_RESOLUTION,
  DEFAULT_VIDEO_DURATION,
  DEFAULT_VIDEO_RESOLUTION,
  FREE_EDIT_V2_5_MODE_ID,
  FREE_EDIT_V3_MODE_ID,
  getScail2VideoCost,
  type LabModeConfig,
  type UnifiedLabModeId,
} from '@/features/generation/labModeConfig'
import {
  getWan22VideoV2Cost,
  type Wan22VideoV2ResolutionPreset,
} from '@/features/generation/imageToVideo'
import { getRuntimeTaskPrice } from '@/config/runtime'

export const DEFAULT_EDIT_LORA_STRENGTH = 1

export const isScail2ModeId = (modeId: UnifiedLabModeId) => (
  modeId === 'scail2_action_transfer'
  || modeId === 'scail2_video_replacement'
  || modeId === 'scail2_face_swap_v2'
)

export const isLtxLabModeId = (modeId: UnifiedLabModeId) => (
  modeId === 'ltx_video' || modeId === 'ltx_video_v2' || modeId === 'ltx_t2v'
)

export const getDefaultResolutionForMode = (modeId: UnifiedLabModeId) => (
  modeId === 'ltx25_video_upscale'
    ? '1080p'
    : modeId === 'face_video'
    ? DEFAULT_FACE_VIDEO_RESOLUTION
    : isLtxLabModeId(modeId)
      ? DEFAULT_LTX_VIDEO_RESOLUTION
      : DEFAULT_VIDEO_RESOLUTION
)

export type GetLabModeCostOptions = {
  mode: LabModeConfig
  taskTypeOverride?: string
  uploadedReferenceCount: number
  resolution: string
  duration: string
  wan22ResolutionPreset: Wan22VideoV2ResolutionPreset
  hasCharacter?: boolean
}

export const getLabModeCost = ({
  mode,
  taskTypeOverride,
  uploadedReferenceCount,
  resolution,
  duration,
  wan22ResolutionPreset,
  hasCharacter = false,
}: GetLabModeCostOptions) => {
  const taskType = taskTypeOverride ?? mode.taskType
  let defaultCost: number
  if (mode.id === 'edit') {
    defaultCost = uploadedReferenceCount >= 2 ? 6 : 2
    return getRuntimeTaskPrice(taskType, defaultCost, {
      engine: taskType === 'img2img_lora' ? 'addon' : 'standard',
      input_count: Math.max(1, Math.min(2, uploadedReferenceCount)),
    })
  }

  if (mode.id === FREE_EDIT_V3_MODE_ID) {
    return getRuntimeTaskPrice(taskType, 5)
  }

  if (mode.id === FREE_EDIT_V2_5_MODE_ID) {
    defaultCost = uploadedReferenceCount >= 2 ? 7 : 3
    return getRuntimeTaskPrice(taskType, defaultCost, {
      input_count: Math.max(1, Math.min(2, uploadedReferenceCount)),
    })
  }

  if (mode.id === 'custom_video' || mode.id === 'wan22_video_v2') {
    defaultCost = getWan22VideoV2Cost(wan22ResolutionPreset, duration)
    return getRuntimeTaskPrice(taskType, defaultCost, {
      input_count: Math.max(1, Math.min(2, uploadedReferenceCount)),
      resolution: wan22ResolutionPreset,
      duration,
    })
  }

  if (mode.id === 'face_video') {
    defaultCost = resolution === '1024' ? 36 : 18
    return getRuntimeTaskPrice(taskType, defaultCost, { resolution })
  }

  if (isLtxLabModeId(mode.id)) {
    let multiplier = 1
    if (duration === '10') multiplier = 2
    else if (duration === '15') multiplier = 3
    else if (duration === '20') multiplier = 4
    defaultCost = mode.id === 'ltx_t2v' && hasCharacter
      ? 12 * multiplier
      : 10 * multiplier
    const modeKey = mode.id === 'ltx_t2v'
      ? (hasCharacter ? 'character' : 'standard')
      : (uploadedReferenceCount >= 2 ? 'flf2v' : 'i2v')
    return getRuntimeTaskPrice(taskType, defaultCost, {
      mode: modeKey,
      resolution,
      duration,
    })
  }

  if (isScail2ModeId(mode.id)) {
    defaultCost = getScail2VideoCost(duration || DEFAULT_VIDEO_DURATION, mode.id)
    return getRuntimeTaskPrice(taskType, defaultCost, { duration })
  }

  return getRuntimeTaskPrice(taskType, mode.baseCost)
}

export const getLabCostHintKey = (modeId: UnifiedLabModeId) => {
  if (modeId === 'edit') {
    return 'lab.workbench.cost_hints.edit'
  }

  if (modeId === FREE_EDIT_V3_MODE_ID) {
    return 'lab.workbench.cost_hints.edit_v3'
  }

  if (modeId === FREE_EDIT_V2_5_MODE_ID) {
    return 'lab.workbench.cost_hints.edit_v2_5'
  }

  if (modeId === 'custom_video') {
    return 'lab.workbench.cost_hints.custom_video'
  }

  if (modeId === 'face_video') {
    return 'lab.workbench.cost_hints.face_video'
  }

  if (modeId === 'ltx25_video_upscale') {
    return 'lab.workbench.cost_hints.ltx25_video_upscale'
  }

  if (isLtxLabModeId(modeId)) {
    return modeId === 'ltx_t2v' ? 'lab.workbench.cost_hints.ltx_t2v' : 'lab.workbench.cost_hints.ltx_video'
  }

  if (modeId === 'wan22_video_v2') {
    return 'lab.workbench.cost_hints.wan22_video_v2'
  }

  if (isScail2ModeId(modeId)) {
    return 'lab.workbench.cost_hints.scail2_video'
  }

  return ''
}
