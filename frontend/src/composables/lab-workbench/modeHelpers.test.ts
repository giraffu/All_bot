// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'

import { getLabModeConfig, type LabModeConfig } from '@/features/generation/labModeConfig'
import {
  getDefaultResolutionForMode,
  getLabCostHintKey,
  getLabModeCost,
  isLtxLabModeId,
  isScail2ModeId,
} from './modeHelpers'

describe('lab workbench mode helpers', () => {
  it('uses a runtime task price override for the displayed web cost', () => {
    window.__ALLBOT_TASK_PRICE_OVERRIDES__ = Object.freeze({
      txt2img: 17,
      ltx_t2v_ic: 23,
    })
    const mode = {
      id: 'txt2img',
      taskType: 'txt2img',
      baseCost: 2,
    } as LabModeConfig

    expect(getLabModeCost({
      mode,
      uploadedReferenceCount: 0,
      resolution: '512',
      duration: '5',
      wan22ResolutionPreset: 'preview',
    })).toBe(17)

    expect(getLabModeCost({
      mode: getLabModeConfig('ltx_t2v'),
      taskTypeOverride: 'ltx_t2v_ic',
      uploadedReferenceCount: 0,
      resolution: '768x448',
      duration: '5',
      wan22ResolutionPreset: 'preview',
      hasCharacter: true,
    })).toBe(23)
    window.__ALLBOT_TASK_PRICE_OVERRIDES__ = undefined
  })

  it('uses the condition-specific runtime price for double-image fusion', () => {
    window.__ALLBOT_TASK_PRICING__ = {
      prices: Object.freeze({
        'free_edit_v2_5::input_count=1': 4,
        'free_edit_v2_5::input_count=2': 11,
      }),
      variants: Object.freeze([
        {
          variant_id: 'free_edit_v2_5::input_count=1',
          task_types: ['free_edit_v2_5'],
          conditions: { input_count: '1' },
        },
        {
          variant_id: 'free_edit_v2_5::input_count=2',
          task_types: ['free_edit_v2_5'],
          conditions: { input_count: '2' },
        },
      ]),
    }

    expect(getLabModeCost({
      mode: getLabModeConfig('edit_v2_5'),
      uploadedReferenceCount: 1,
      resolution: '512',
      duration: '5',
      wan22ResolutionPreset: 'preview',
    })).toBe(4)
    expect(getLabModeCost({
      mode: getLabModeConfig('edit_v2_5'),
      uploadedReferenceCount: 2,
      resolution: '512',
      duration: '5',
      wan22ResolutionPreset: 'preview',
    })).toBe(11)
    window.__ALLBOT_TASK_PRICING__ = undefined
  })
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
      mode: getLabModeConfig('edit_v2_5'),
      uploadedReferenceCount: 2,
      resolution: '512',
      duration: '5',
      wan22ResolutionPreset: 'preview',
    })).toBe(7)
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
      mode: getLabModeConfig('ltx_t2v'),
      uploadedReferenceCount: 0,
      resolution: '1280x704',
      duration: '15',
      wan22ResolutionPreset: 'preview',
    })).toBe(30)
    expect(getLabModeCost({
      mode: getLabModeConfig('ltx_t2v'),
      uploadedReferenceCount: 0,
      resolution: '768x448',
      duration: '5',
      wan22ResolutionPreset: 'preview',
      hasCharacter: true,
    })).toBe(12)
    expect(getLabModeCost({
      mode: getLabModeConfig('ltx_t2v'),
      uploadedReferenceCount: 0,
      resolution: '768x448',
      duration: '20',
      wan22ResolutionPreset: 'preview',
      hasCharacter: true,
    })).toBe(48)
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
    expect(getLabCostHintKey('ltx25_video_upscale')).toBe('lab.workbench.cost_hints.ltx25_video_upscale')
    expect(getLabCostHintKey('scail2_action_transfer')).toBe('lab.workbench.cost_hints.scail2_video')
    expect(getLabCostHintKey('scail2_face_swap_v2')).toBe('lab.workbench.cost_hints.scail2_video')
    expect(getLabCostHintKey('txt2img')).toBe('')
  })
})
