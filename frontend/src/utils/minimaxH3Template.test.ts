import { describe, expect, it } from 'vitest'
import { areFrameAspectRatiosCompatible, getMinimaxH3TemplateCost } from '@/utils/minimaxH3Template'

describe('MiniMax H3 template helpers', () => {
  it('enforces a one-percent first/last frame aspect tolerance', () => {
    expect(areFrameAspectRatiosCompatible({ width: 1000, height: 1000 }, { width: 1009, height: 1000 })).toBe(true)
    expect(areFrameAspectRatiosCompatible({ width: 1000, height: 1000 }, { width: 1011, height: 1000 })).toBe(false)
  })

  it('uses locked resolution and duration for cost', () => {
    expect(getMinimaxH3TemplateCost('standard', 10)).toBe(40)
  })
})
