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
    }
  })

  it('shows MiniMax H3 and hides all LTX generation workbenches', async () => {
    const { UNIFIED_LAB_MODES } = await import('./labModeConfig')
    const visibleModeIds = UNIFIED_LAB_MODES.map(mode => mode.id)

    expect(visibleModeIds).toContain('minimax_h3')
    expect(visibleModeIds).not.toContain('ltx_video')
    expect(visibleModeIds).not.toContain('ltx_video_v2')
    expect(visibleModeIds).not.toContain('ltx_t2v')
  })
})
