import { describe, expect, it } from 'vitest'

import {
  RUNPOD_FALLBACK_PROFILES,
  isRunPodManualAgentId,
} from './runpodProfiles'

describe('runpodProfiles', () => {
  it('keeps the LTX T2V manual profile available when the API is unavailable', () => {
    expect(RUNPOD_FALLBACK_PROFILES).toContainEqual({
      profile: 'ltx_t2v',
      label: 'ltx_t2v / Sulphur + Ingredients',
      supported_task_types: ['ltx_t2v', 'ltx_t2v_ic'],
    })
  })

  it('recognizes LTX T2V manual workers through the shared agent-id contract', () => {
    expect(isRunPodManualAgentId('runpod_prod_ltx_t2v_manual_01')).toBe(true)
    expect(isRunPodManualAgentId('runpod_test_ltx_t2v_canary_01')).toBe(false)
  })
})
