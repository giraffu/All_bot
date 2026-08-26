// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from 'vitest'
import { isGallerySubmissionEligible } from '@/utils/gallerySubmissionEligibility'

describe('isGallerySubmissionEligible', () => {
  beforeEach(() => {
    window.__ALLBOT_CONFIG__ = {
      enable_ltx_video: true,
      enable_minimax_h3: false,
    }
  })

  it('keeps LTX contribution open while H3 Pro is disabled in prod', () => {
    expect(isGallerySubmissionEligible({
      type: 'ltx_video', allow_contribute: true,
    })).toBe(true)
    expect(isGallerySubmissionEligible({
      type: 'ltx_video_flf2v', allow_contribute: true,
    })).toBe(true)
    expect(isGallerySubmissionEligible({
      type: 'minimax_h3_i2v', allow_contribute: true,
    })).toBe(false)
  })

  it('allows H3 image-mode contribution only when the test feature is enabled', () => {
    window.__ALLBOT_CONFIG__ = {
      enable_minimax_h3: true,
      enable_minimax_h3_ref2v: true,
    }

    expect(isGallerySubmissionEligible({
      type: 'minimax_h3_i2v', allow_contribute: true,
    })).toBe(true)
    expect(isGallerySubmissionEligible({
      type: 'minimax_h3_flf2v', allow_contribute: true,
    })).toBe(true)
    expect(isGallerySubmissionEligible({
      type: 'minimax_h3_ref2v', allow_contribute: true,
    })).toBe(true)
    expect(isGallerySubmissionEligible({
      type: 'minimax_h3_t2v', allow_contribute: true,
    })).toBe(false)
  })

  it('rejects template-derived records even for supported types', () => {
    expect(isGallerySubmissionEligible({
      type: 'minimax_h3_i2v', allow_contribute: false,
    })).toBe(false)
  })
})
