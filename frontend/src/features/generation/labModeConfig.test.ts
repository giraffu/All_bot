import { describe, expect, it } from 'vitest'

import { DEFAULT_WAN22_VIDEO_V2_COST } from './imageToVideo'
import { getLabModeConfig } from './labModeConfig'

describe('labModeConfig', () => {
  it('uses the default wan22 v2 cost for the lab mode tag', () => {
    expect(getLabModeConfig('wan22_video_v2').baseCost).toBe(DEFAULT_WAN22_VIDEO_V2_COST)
    expect(getLabModeConfig('wan22_video_v2').baseCost).toBe(6)
  })
})
