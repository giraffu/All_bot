import { describe, expect, it } from 'vitest'

import { DEFAULT_WAN22_VIDEO_V2_COST } from './imageToVideo'
import {
  DEFAULT_LAB_MODE_ID,
  LAB_MODE_CONFIGS,
  SCAIL2_SHORT_VIDEO_DURATION_OPTIONS,
  SCAIL2_VIDEO_DURATION_OPTIONS,
  UNIFIED_LAB_MODES,
  WEB_LTX_T2V_ENABLED,
  MINIMAX_H3_ADDON_OPTIONS,
  getLabModeConfig,
  getScail2VideoDurationOptionsForMotionVideo,
  getScail2VideoCost,
  resolveLabModeIdFromTaskType,
} from './labModeConfig'

describe('labModeConfig', () => {
  it('publishes per-addon strength recommendations and prompt guides', () => {
    const sexPose = MINIMAX_H3_ADDON_OPTIONS.find(option => option.value === 'sex_pose')
    const vagina = MINIMAX_H3_ADDON_OPTIONS.find(option => option.value === 'vagina')

    expect(sexPose).toMatchObject({
      defaultStrength: 0.5,
      recommendedMinStrength: 0.1,
      recommendedMaxStrength: 0.5,
      strengthHintKey: 'lab.workbench.minimax_h3_addon_guides.sex_pose_strength',
      promptGuideKey: 'lab.workbench.minimax_h3_addon_guides.sex_pose_prompt',
    })
    expect(vagina).toMatchObject({
      defaultStrength: 1,
      recommendedMinStrength: 1,
      recommendedMaxStrength: 1,
      strengthHintKey: 'lab.workbench.minimax_h3_addon_guides.vagina_strength',
      promptGuideKey: 'lab.workbench.minimax_h3_addon_guides.vagina_prompt',
    })
    expect(MINIMAX_H3_ADDON_OPTIONS.every(option => option.strengthHintKey && option.promptGuideKey)).toBe(true)
  })
  it('hides character reference and text-to-video modes when production LTX is disabled', () => {
    expect(LAB_MODE_CONFIGS.map(item => item.id)).toContain('character_reference')
    expect(WEB_LTX_T2V_ENABLED).toBe(false)
    expect(UNIFIED_LAB_MODES.map(item => item.id)).not.toContain('character_reference')
    expect(UNIFIED_LAB_MODES.map(item => item.id)).not.toContain('ltx_t2v')
    expect(resolveLabModeIdFromTaskType('character_reference')).toBe(
      DEFAULT_LAB_MODE_ID,
    )
  })

  it('uses the default wan22 v2 cost for the lab mode tag', () => {
    expect(getLabModeConfig('wan22_video_v2').baseCost).toBe(DEFAULT_WAN22_VIDEO_V2_COST)
    expect(getLabModeConfig('wan22_video_v2').baseCost).toBe(6)
  })

  it('shows single-image free edit v3 next to the original free edit mode', () => {
    const mode = getLabModeConfig('edit_v3')
    const modeIds = UNIFIED_LAB_MODES.map(item => item.id)

    expect(mode.taskType).toBe('pornmaster_flux2_edit_bf16')
    expect(mode.baseCost).toBe(5)
    expect(mode.supportsEditLora).toBe(false)
    expect(mode.maxImages).toBe(1)
    expect(modeIds.slice(0, 3)).toEqual(['edit', 'edit_v2_5', 'edit_v3'])
    expect(resolveLabModeIdFromTaskType('pornmaster_flux2_edit_bf16')).toBe('edit_v3')
    expect(resolveLabModeIdFromTaskType('pornmaster_flux2_single_edit')).toBe('edit_v3')
    expect(resolveLabModeIdFromTaskType('pornmaster_flux2_multi_edit')).toBe('edit_v3')
  })

  it('shows free edit v2.5 as a one-or-two-image single-stage mode', () => {
    const mode = getLabModeConfig('edit_v2_5')

    expect(mode.taskType).toBe('free_edit_v2_5')
    expect(mode.baseCost).toBe(3)
    expect(mode.supportsEditLora).toBe(false)
    expect(mode.maxImages).toBe(2)
    expect(resolveLabModeIdFromTaskType('free_edit_v2_5')).toBe('edit_v2_5')
  })

  it('shows the current two-credit price for direct and random face swap', () => {
    const directMode = getLabModeConfig('face_swap')
    const randomMode = getLabModeConfig('random_faceswap')

    expect(directMode.baseCost).toBe(2)
    expect(randomMode.taskType).toBe('random_faceswap')
    expect(randomMode.maxImages).toBe(1)
    expect(randomMode.baseCost).toBe(2)
    expect(randomMode.supportsPromptInput).toBe(false)
    expect(UNIFIED_LAB_MODES.map(item => item.id)).toContain('random_faceswap')
    expect(resolveLabModeIdFromTaskType('random_faceswap')).toBe('random_faceswap')
    expect(resolveLabModeIdFromTaskType('image2video')).toBe('custom_video')
    expect(resolveLabModeIdFromTaskType('image_to_video')).toBe('custom_video')
  })

  it('allows one uploaded environment image for LTX text-to-video references', () => {
    const mode = getLabModeConfig('ltx_t2v')

    expect(mode.supportsUpload).toBe(true)
    expect(mode.maxImages).toBe(1)
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
    expect(resolveLabModeIdFromTaskType('face_video')).toBe('scail2_face_swap_v2')
    expect(SCAIL2_VIDEO_DURATION_OPTIONS.map(option => option.value)).toEqual(['5', '8', '10', '15', '20'])
    expect(SCAIL2_SHORT_VIDEO_DURATION_OPTIONS.map(option => option.value)).toEqual(['5', '8'])
    expect(getScail2VideoCost('5')).toBe(40)
    expect(getScail2VideoCost('8s')).toBe(80)
    expect(getScail2VideoCost('10', 'scail2_action_transfer')).toBe(120)
    expect(getScail2VideoCost('15', 'scail2_action_transfer')).toBe(180)
    expect(getScail2VideoCost('20', 'scail2_action_transfer')).toBe(260)
    expect(UNIFIED_LAB_MODES.map(item => item.id)).not.toContain('scail2_action_transfer_long')
    expect(UNIFIED_LAB_MODES.map(item => item.id)).not.toContain('face_video')
  })

  it('keeps LTX video dubbing out of the user-facing lab modes', () => {
    expect(UNIFIED_LAB_MODES.map(mode => mode.id)).not.toContain('ltx_video_audio')
    expect(resolveLabModeIdFromTaskType('ltx_video')).toBe('ltx_video')
    expect(resolveLabModeIdFromTaskType('ltx_video_audio')).toBe(DEFAULT_LAB_MODE_ID)
  })

  it('keeps i2i draw out of the web lab modes while it is disabled', () => {
    expect(UNIFIED_LAB_MODES.map(mode => mode.id)).not.toContain('i2i_draw')
    expect(resolveLabModeIdFromTaskType('i2i_draw')).toBe(DEFAULT_LAB_MODE_ID)
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
