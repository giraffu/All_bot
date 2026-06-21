import {
  DEFAULT_FACE_VIDEO_RESOLUTION,
  DEFAULT_LTX_VIDEO_RESOLUTION,
  DEFAULT_VIDEO_DURATION,
  DEFAULT_VIDEO_RESOLUTION,
  getScail2VideoCost,
  type LabModeConfig,
  type UnifiedLabModeId,
} from '@/features/generation/labModeConfig'
import {
  getWan22VideoV2Cost,
  type Wan22VideoV2ResolutionPreset,
} from '@/features/generation/imageToVideo'

export const DEFAULT_EDIT_LORA_STRENGTH = 1

export const isScail2ModeId = (modeId: UnifiedLabModeId) => (
  modeId === 'scail2_action_transfer'
  || modeId === 'scail2_video_replacement'
  || modeId === 'scail2_face_swap_v2'
)

export const isLtxLabModeId = (modeId: UnifiedLabModeId) => (
  modeId === 'ltx_video' || modeId === 'ltx_video_audio'
)

export const getDefaultResolutionForMode = (modeId: UnifiedLabModeId) => (
  modeId === 'face_video'
    ? DEFAULT_FACE_VIDEO_RESOLUTION
    : isLtxLabModeId(modeId)
      ? DEFAULT_LTX_VIDEO_RESOLUTION
      : DEFAULT_VIDEO_RESOLUTION
)

export type GetLabModeCostOptions = {
  mode: LabModeConfig
  uploadedReferenceCount: number
  resolution: string
  duration: string
  wan22ResolutionPreset: Wan22VideoV2ResolutionPreset
}

export const getLabModeCost = ({
  mode,
  uploadedReferenceCount,
  resolution,
  duration,
  wan22ResolutionPreset,
}: GetLabModeCostOptions) => {
  if (mode.id === 'edit') {
    return uploadedReferenceCount >= 2 ? 6 : 2
  }

  if (mode.id === 'custom_video' || mode.id === 'wan22_video_v2') {
    return getWan22VideoV2Cost(wan22ResolutionPreset, duration)
  }

  if (mode.id === 'face_video') {
    return resolution === '1024' ? 36 : 18
  }

  if (isLtxLabModeId(mode.id)) {
    let multiplier = 1
    if (duration === '10') multiplier = 2
    else if (duration === '15') multiplier = 3
    else if (duration === '20') multiplier = 4
    return 10 * multiplier
  }

  if (isScail2ModeId(mode.id)) {
    return getScail2VideoCost(duration || DEFAULT_VIDEO_DURATION)
  }

  return mode.baseCost
}

export const getLabCostHintKey = (modeId: UnifiedLabModeId) => {
  if (modeId === 'edit') {
    return 'lab.workbench.cost_hints.edit'
  }

  if (modeId === 'custom_video') {
    return 'lab.workbench.cost_hints.custom_video'
  }

  if (modeId === 'face_video') {
    return 'lab.workbench.cost_hints.face_video'
  }

  if (isLtxLabModeId(modeId)) {
    return modeId === 'ltx_video_audio'
      ? 'lab.workbench.cost_hints.ltx_video_audio'
      : 'lab.workbench.cost_hints.ltx_video'
  }

  if (modeId === 'wan22_video_v2') {
    return 'lab.workbench.cost_hints.wan22_video_v2'
  }

  if (isScail2ModeId(modeId)) {
    return 'lab.workbench.cost_hints.scail2_video'
  }

  return ''
}
