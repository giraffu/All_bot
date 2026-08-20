// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('test Web video feature visibility', () => {
  beforeEach(() => {
    vi.resetModules()
    window.__ALLBOT_CONFIG__ = {
      enable_ltx_video: false,
      enable_ltx_video_v2: false,
      enable_ltx_t2v: false,
      enable_minimax_h3: true,
      enable_minimax_h3_entry: false,
      enable_minimax_h3_ref2v: true,
    }
  })

  it('keeps the H3 card hidden while its direct test capability is enabled', async () => {
    const { UNIFIED_LAB_MODES, resolveLabModeIdFromTaskType } = await import('./labModeConfig')
    const visibleModeIds = UNIFIED_LAB_MODES.map(mode => mode.id)

    expect(visibleModeIds).not.toContain('minimax_h3')
    expect(visibleModeIds).not.toContain('ltx_video')
    expect(visibleModeIds).not.toContain('ltx_video_v2')
    expect(visibleModeIds).not.toContain('ltx_t2v')
    expect(resolveLabModeIdFromTaskType('minimax_h3_ref2v')).toBe('minimax_h3')
  })

  it('rejects the REF2V deep link when its independent capability flag is off', async () => {
    window.__ALLBOT_CONFIG__ = {
      ...window.__ALLBOT_CONFIG__,
      enable_minimax_h3_ref2v: false,
    }
    vi.resetModules()

    const { DEFAULT_LAB_MODE_ID, resolveLabModeIdFromTaskType } = await import('./labModeConfig')

    expect(resolveLabModeIdFromTaskType('minimax_h3_ref2v')).toBe(DEFAULT_LAB_MODE_ID)
  })
})
