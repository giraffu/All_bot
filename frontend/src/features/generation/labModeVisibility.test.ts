// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('test Web video feature visibility', () => {
  beforeEach(() => {
    vi.resetModules()
    window.__ALLBOT_CONFIG__ = {
      enable_ltx_video: true,
      enable_ltx_video_v2: false,
      enable_ltx_t2v: false,
      enable_character_assets: true,
      enable_character_assets_entry: false,
      enable_minimax_h3: true,
      enable_minimax_h3_entry: false,
      enable_minimax_h3_ref2v: true,
    }
  })

  it('shows original advanced video while hiding H3 Pro and character entry cards', async () => {
    const { UNIFIED_LAB_MODES, resolveLabModeIdFromTaskType } = await import('./labModeConfig')
    const visibleModeIds = UNIFIED_LAB_MODES.map(mode => mode.id)

    expect(visibleModeIds).toContain('ltx_video')
    expect(visibleModeIds).not.toContain('minimax_h3')
    expect(visibleModeIds).not.toContain('character_reference')
    expect(visibleModeIds).not.toContain('ltx_video_v2')
    expect(visibleModeIds).not.toContain('ltx_t2v')
    expect(resolveLabModeIdFromTaskType('character_reference')).toBe('character_reference')
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
