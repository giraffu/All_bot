import { describe, expect, it } from 'vitest'

import {
  buildDefaultLtxVideoLoraItem,
  DEFAULT_WAN22_VIDEO_V2_COST,
  DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET,
  DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
  WAN22_VIDEO_V2_RESOLUTION_OPTIONS,
  getDefaultImageToVideoLoraSelection,
  getImageToVideoPayloadLoraName,
  getImageToVideoPayloadLoraStrength,
  normalizeWan22VideoV2ResolutionPreset,
  normalizeLtxVideoLoraItems,
  NO_LTX_VIDEO_LORA,
} from './imageToVideo'

describe('imageToVideo LTX LoRA helpers', () => {
  it('returns none as default selection for ltx_video', () => {
    expect(getDefaultImageToVideoLoraSelection('ltx_video')).toBe(NO_LTX_VIDEO_LORA)
  })

  it('maps selected ltx lora to payload name and default strength', () => {
    const selection = 'ltx2.3/pussyjob_v1.1_merged_ltx23.safetensors'

    expect(getImageToVideoPayloadLoraName('ltx_video', selection)).toBe(selection)
    expect(getImageToVideoPayloadLoraStrength('ltx_video', selection)).toBe(0.8)
  })

  it('does not emit ltx lora payload when none is selected', () => {
    expect(getImageToVideoPayloadLoraName('ltx_video', NO_LTX_VIDEO_LORA)).toBeUndefined()
    expect(getImageToVideoPayloadLoraStrength('ltx_video', NO_LTX_VIDEO_LORA)).toBeUndefined()
  })

  it('builds default ltx video lora items from catalog defaults', () => {
    expect(
      buildDefaultLtxVideoLoraItem('ltx2.3/st0mach_bulge_ltx23_v1.1.safetensors'),
    ).toEqual({
      name: 'ltx2.3/st0mach_bulge_ltx23_v1.1.safetensors',
      strength: 0.8,
    })
  })

  it('normalizes ltx video lora items with dedupe and clamp', () => {
    expect(normalizeLtxVideoLoraItems([
      {
        name: 'ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors',
        strength: 3,
      },
      {
        name: 'ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors',
        strength: 0.4,
      },
      {
        name: 'ltx2.3/SynthPussy_01_rank32.safetensors',
        strength: 0.76,
      },
    ])).toEqual([
      {
        name: 'ltx2.3/LTX2.3_reasoning_I2V_V3.safetensors',
        strength: 2,
      },
      {
        name: 'ltx2.3/SynthPussy_01_rank32.safetensors',
        strength: 0.76,
      },
    ])
  })

  it('exposes the default wan22 negative prompt preset', () => {
    expect(DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT).toContain('censored')
    expect(DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT).toContain('voluminous eyelashes')
  })

  it('exposes the wan22 fast-lowest resolution option', () => {
    expect(DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET).toBe('preview')
    expect(DEFAULT_WAN22_VIDEO_V2_COST).toBe(8)
    expect(WAN22_VIDEO_V2_RESOLUTION_OPTIONS[0]).toEqual({
      value: 'preview',
      label: '极速',
      description: '约 512p，最低价，生成更快',
      cost: 8,
    })
    expect(WAN22_VIDEO_V2_RESOLUTION_OPTIONS[1].description).toBe('约 720p，平衡画质与速度')
    expect(WAN22_VIDEO_V2_RESOLUTION_OPTIONS[2].description).toBe('约 810p，更清晰，生成更慢')
    expect(WAN22_VIDEO_V2_RESOLUTION_OPTIONS.map(option => option.value)).toEqual([
      'preview',
      'standard',
      'hd',
    ])
  })

  it('normalizes legacy wan22 fast resolution to preview', () => {
    expect(normalizeWan22VideoV2ResolutionPreset('fast')).toBe('preview')
    expect(normalizeWan22VideoV2ResolutionPreset('0.36 MP - Small')).toBe('preview')
  })
})
