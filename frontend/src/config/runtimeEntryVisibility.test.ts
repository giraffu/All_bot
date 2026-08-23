// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { hydrateRuntimeEntryVisibility } from './runtimeEntryVisibility'

describe('runtime entry visibility hydration', () => {
  beforeEach(() => {
    window.__ALLBOT_CONFIG__ = Object.freeze({
      api_base_url: 'https://api-test.example.com/api',
      enable_ltx_video: true,
      enable_minimax_h3: true,
      enable_character_assets: true,
      enable_minimax_h3_entry: false,
    })
    vi.restoreAllMocks()
  })

  it('loads safe entry flags before the application modules are mounted', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        flags: {
          enable_ltx_video_entry: true,
          enable_minimax_h3_entry: true,
          enable_character_assets_entry: false,
          enable_gallery_minimax_h3_entry: false,
        },
      }),
    })

    await expect(hydrateRuntimeEntryVisibility(fetchMock)).resolves.toBe(true)

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api-test.example.com/api/app/entry-visibility',
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(window.__ALLBOT_CONFIG__).toMatchObject({
      enable_ltx_video: true,
      enable_minimax_h3_entry: true,
      enable_gallery_minimax_h3_entry: false,
    })
  })

  it('keeps release-time fallback flags when the runtime endpoint is unavailable', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('offline'))

    await expect(hydrateRuntimeEntryVisibility(fetchMock)).resolves.toBe(false)

    expect(window.__ALLBOT_CONFIG__?.enable_minimax_h3_entry).toBe(false)
  })
})
