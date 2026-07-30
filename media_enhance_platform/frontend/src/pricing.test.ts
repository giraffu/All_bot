import { describe, expect, it } from 'vitest'
import { quotePoints } from './pricing'

describe('quotePoints', () => {
  it('prices image presets as fixed point amounts', () => {
    expect(quotePoints('image_upscale', 2, null)).toBe(2)
    expect(quotePoints('image_upscale', 4, null)).toBe(4)
  })

  it('rounds video pricing to each started ten second unit', () => {
    expect(quotePoints('video_upscale', 2, 10.01)).toBe(10)
    expect(quotePoints('frame_interpolation', 4, 21)).toBe(15)
  })
})
