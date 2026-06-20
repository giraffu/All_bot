import { describe, expect, it } from 'vitest'

import { DEFAULT_WAN22_VIDEO_V2_COST } from './imageToVideo'
import {
  SCAIL2_VIDEO_DURATION_OPTIONS,
  getLabModeConfig,
  getScail2VideoDurationOptionsForMotionVideo,
  getScail2VideoCost,
  resolveLabModeIdFromTaskType,
} from './labModeConfig'

describe('labModeConfig', () => {
  it('uses the default wan22 v2 cost for the lab mode tag', () => {
    expect(getLabModeConfig('wan22_video_v2').baseCost).toBe(DEFAULT_WAN22_VIDEO_V2_COST)
    expect(getLabModeConfig('wan22_video_v2').baseCost).toBe(6)
  })

  it('configures scail2 modes with reference image and motion video slots', () => {
    const actionTransfer = getLabModeConfig('scail2_action_transfer')
    const replacement = getLabModeConfig('scail2_video_replacement')
    const faceSwapV2 = getLabModeConfig('scail2_face_swap_v2')

    for (const mode of [actionTransfer, replacement, faceSwapV2]) {
      expect(mode.supportsUpload).toBe(false)
      expect(mode.supportsVideoOptions).toBe(true)
      expect(mode.supportsResolutionOptions).toBe(false)
      expect(mode.supportsNegativePrompt).toBe(true)
      expect(mode.promptRequired).toBe(false)
      expect(mode.uploadSlots?.map(slot => slot.id)).toEqual(['reference_image', 'motion_video'])
      expect(mode.uploadSlots?.[0]?.accept).toContain('image/')
      expect(mode.uploadSlots?.[1]?.accept).toContain('video/')
    }
  })

  it('resolves scail2 task types and duration pricing', () => {
    expect(resolveLabModeIdFromTaskType('scail2_action_transfer')).toBe('scail2_action_transfer')
    expect(resolveLabModeIdFromTaskType('scail2_video_replacement')).toBe('scail2_video_replacement')
    expect(resolveLabModeIdFromTaskType('scail2_face_swap_v2')).toBe('scail2_face_swap_v2')
    expect(SCAIL2_VIDEO_DURATION_OPTIONS.map(option => option.value)).toEqual(['5', '8'])
    expect(getScail2VideoCost('5')).toBe(40)
    expect(getScail2VideoCost('8s')).toBe(80)
  })

  it('filters scail2 duration options by motion video length', () => {
    expect(getScail2VideoDurationOptionsForMotionVideo(null).map(option => option.value)).toEqual(['5'])
    expect(getScail2VideoDurationOptionsForMotionVideo(6).map(option => option.value)).toEqual(['5'])
    expect(getScail2VideoDurationOptionsForMotionVideo(8).map(option => option.value)).toEqual(['5', '8'])
    expect(getScail2VideoDurationOptionsForMotionVideo(12).map(option => option.value)).toEqual(['5', '8'])
  })
})
