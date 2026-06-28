import { describe, expect, it } from 'vitest'

import { DEFAULT_WAN22_VIDEO_V2_COST } from './imageToVideo'
import {
  DEFAULT_LAB_MODE_ID,
  SCAIL2_SHORT_VIDEO_DURATION_OPTIONS,
  SCAIL2_VIDEO_DURATION_OPTIONS,
  UNIFIED_LAB_MODES,
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

  it('shows free edit v2 next to the original free edit mode', () => {
    const mode = getLabModeConfig('edit_v2')
    const modeIds = UNIFIED_LAB_MODES.map(item => item.id)

    expect(mode.taskType).toBe('pornmaster_flux2_single_edit')
    expect(mode.supportsEditLora).toBe(false)
    expect(mode.maxImages).toBe(2)
    expect(modeIds.slice(0, 2)).toEqual(['edit', 'edit_v2'])
    expect(resolveLabModeIdFromTaskType('pornmaster_flux2_single_edit')).toBe('edit_v2')
    expect(resolveLabModeIdFromTaskType('pornmaster_flux2_multi_edit')).toBe('edit_v2')
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
    expect(resolveLabModeIdFromTaskType('scail2_action_transfer_long')).toBe('scail2_action_transfer')
    expect(resolveLabModeIdFromTaskType('scail2_video_replacement')).toBe('scail2_video_replacement')
    expect(resolveLabModeIdFromTaskType('scail2_face_swap_v2')).toBe('scail2_face_swap_v2')
    expect(SCAIL2_VIDEO_DURATION_OPTIONS.map(option => option.value)).toEqual(['5', '8', '10', '15', '20'])
    expect(SCAIL2_SHORT_VIDEO_DURATION_OPTIONS.map(option => option.value)).toEqual(['5', '8'])
    expect(getScail2VideoCost('5')).toBe(40)
    expect(getScail2VideoCost('8s')).toBe(80)
    expect(getScail2VideoCost('10', 'scail2_action_transfer')).toBe(120)
    expect(getScail2VideoCost('15', 'scail2_action_transfer')).toBe(180)
    expect(getScail2VideoCost('20', 'scail2_action_transfer')).toBe(260)
    expect(UNIFIED_LAB_MODES.map(item => item.id)).not.toContain('scail2_action_transfer_long')
  })

  it('keeps LTX video dubbing out of the user-facing lab modes', () => {
    expect(UNIFIED_LAB_MODES.map(mode => mode.id)).not.toContain('ltx_video_audio')
    expect(resolveLabModeIdFromTaskType('ltx_video')).toBe('ltx_video')
    expect(resolveLabModeIdFromTaskType('ltx_video_audio')).toBe(DEFAULT_LAB_MODE_ID)
  })

  it('filters scail2 duration options by motion video length', () => {
    expect(getScail2VideoDurationOptionsForMotionVideo(null).map(option => option.value)).toEqual(['5'])
    expect(getScail2VideoDurationOptionsForMotionVideo(6).map(option => option.value)).toEqual(['5'])
    expect(getScail2VideoDurationOptionsForMotionVideo(8).map(option => option.value)).toEqual(['5', '8'])
    expect(getScail2VideoDurationOptionsForMotionVideo(12).map(option => option.value)).toEqual(['5', '8', '10'])
    expect(
      getScail2VideoDurationOptionsForMotionVideo(20, 'scail2_action_transfer')
        .map(option => option.value)
    ).toEqual(['5', '8', '10', '15', '20'])
    expect(
      getScail2VideoDurationOptionsForMotionVideo(12, 'scail2_video_replacement')
        .map(option => option.value)
    ).toEqual(['5', '8'])
  })
})
