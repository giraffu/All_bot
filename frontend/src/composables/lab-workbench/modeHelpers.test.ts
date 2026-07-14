import { describe, expect, it } from 'vitest'

import { getLabModeConfig } from '@/features/generation/labModeConfig'
import {
  getDefaultResolutionForMode,
  getLabCostHintKey,
  getLabModeCost,
  isLtxLabModeId,
  isScail2ModeId,
} from './modeHelpers'

describe('lab workbench mode helpers', () => {
  it('identifies grouped video modes', () => {
    expect(isScail2ModeId('scail2_action_transfer')).toBe(true)
    expect(isScail2ModeId('scail2_video_replacement')).toBe(true)
    expect(isScail2ModeId('scail2_face_swap_v2')).toBe(true)
    expect(isScail2ModeId('ltx_video')).toBe(false)
    expect(isLtxLabModeId('ltx_video')).toBe(true)
    expect(isLtxLabModeId('wan22_video_v2')).toBe(false)
  })

  it('resolves default resolution per mode family', () => {
    expect(getDefaultResolutionForMode('face_video')).toBe('720')
    expect(getDefaultResolutionForMode('ltx_video')).toBe('1280x704')
    expect(getDefaultResolutionForMode('edit')).toBe('512')
  })

  it('keeps dynamic cost behavior compatible with the old facade', () => {
    expect(getLabModeCost({
      mode: getLabModeConfig('edit'),
      uploadedReferenceCount: 1,
      resolution: '512',
      duration: '5',
      wan22ResolutionPreset: 'preview',
    })).toBe(2)
    expect(getLabModeCost({
      mode: getLabModeConfig('edit'),
      uploadedReferenceCount: 2,
      resolution: '512',
      duration: '5',
      wan22ResolutionPreset: 'preview',
    })).toBe(6)
    expect(getLabModeCost({
      mode: getLabModeConfig('edit_v3'),
      uploadedReferenceCount: 1,
      resolution: '512',
      duration: '5',
      wan22ResolutionPreset: 'preview',
    })).toBe(5)
    expect(getLabModeCost({
      mode: getLabModeConfig('wan22_video_v2'),
      uploadedReferenceCount: 1,
      resolution: '512',
      duration: '8',
      wan22ResolutionPreset: 'small',
    })).toBe(24)
    expect(getLabModeCost({
      mode: getLabModeConfig('ltx_video'),
      uploadedReferenceCount: 1,
      resolution: '1280x704',
      duration: '20',
      wan22ResolutionPreset: 'preview',
    })).toBe(40)
    expect(getLabModeCost({
      mode: getLabModeConfig('scail2_video_replacement'),
      uploadedReferenceCount: 0,
      resolution: '512',
      duration: '8',
      wan22ResolutionPreset: 'preview',
    })).toBe(80)
    expect(getLabModeCost({
      mode: getLabModeConfig('scail2_action_transfer'),
      uploadedReferenceCount: 0,
      resolution: '512',
      duration: '20',
      wan22ResolutionPreset: 'preview',
    })).toBe(260)
  })

  it('keeps cost hint keys stable', () => {
    expect(getLabCostHintKey('edit')).toBe('lab.workbench.cost_hints.edit')
    expect(getLabCostHintKey('edit_v3')).toBe('lab.workbench.cost_hints.edit_v3')
    expect(getLabCostHintKey('custom_video')).toBe('lab.workbench.cost_hints.custom_video')
    expect(getLabCostHintKey('ltx_video')).toBe('lab.workbench.cost_hints.ltx_video')
    expect(getLabCostHintKey('scail2_action_transfer')).toBe('lab.workbench.cost_hints.scail2_video')
    expect(getLabCostHintKey('scail2_face_swap_v2')).toBe('lab.workbench.cost_hints.scail2_video')
    expect(getLabCostHintKey('txt2img')).toBe('')
  })
})
