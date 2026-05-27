import { describe, expect, it } from 'vitest'

import {
  getDefaultImageToVideoLoraSelection,
  getImageToVideoPayloadLoraName,
  getImageToVideoPayloadLoraStrength,
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
})
