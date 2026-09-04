import { describe, expect, it } from 'vitest'
import { areFrameAspectRatiosCompatible, getMinimaxH3Cost, getMinimaxH3TemplateCost } from '@/utils/minimaxH3Template'

describe('MiniMax H3 template helpers', () => {
  it('enforces a one-percent first/last frame aspect tolerance', () => {
    expect(areFrameAspectRatiosCompatible({ width: 1000, height: 1000 }, { width: 1009, height: 1000 })).toBe(true)
    expect(areFrameAspectRatiosCompatible({ width: 1000, height: 1000 }, { width: 1011, height: 1000 })).toBe(false)
  })

  it('uses locked resolution and duration for cost', () => {
    expect(getMinimaxH3TemplateCost('standard', 10)).toBe(36)
    expect(getMinimaxH3TemplateCost('standard', 10, 'ref2v')).toBe(37)
  })

  it('composes reference audio and video multipliers with ceiling rounding', () => {
    expect(getMinimaxH3Cost('ref2v', 'hd', 15, { referenceAudio: true })).toBe(101)
    expect(getMinimaxH3Cost('ref2v', 'hd', 15, { referenceVideoDuration: 3 })).toBe(128)
    expect(getMinimaxH3Cost('ref2v', 'hd', 15, { referenceVideoDuration: 5 })).toBe(146)
    expect(getMinimaxH3Cost('ref2v', 'hd', 15, { referenceVideoDuration: 10 })).toBe(201)
    expect(getMinimaxH3Cost('ref2v', 'hd', 15, { referenceVideoDuration: 15 })).toBe(255)
    expect(getMinimaxH3Cost('ref2v', 'hd', 15, {
      referenceAudio: true,
      referenceVideoDuration: 15,
    })).toBe(281)
  })
})
