// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from 'vitest'

import { getCanonicalTemplateTaskType } from '@/constants/templateTaskMeta'

describe('template task feature availability', () => {
  beforeEach(() => {
    window.__ALLBOT_CONFIG__ = {
      enable_ltx_video: true,
      enable_minimax_h3: false,
    }
  })

  it('opens LTX apply and rejects H3 Pro apply in prod', () => {
    expect(getCanonicalTemplateTaskType('ltx_video')).toBe('ltx_video')
    expect(getCanonicalTemplateTaskType('ltx_video_flf2v')).toBe('ltx_video')
    expect(getCanonicalTemplateTaskType('minimax_h3_i2v')).toBeNull()
    expect(getCanonicalTemplateTaskType('minimax_h3_flf2v')).toBeNull()
  })

  it('keeps H3 Pro apply available in the test feature set', () => {
    window.__ALLBOT_CONFIG__ = {
      enable_minimax_h3: true,
      enable_minimax_h3_ref2v: true,
    }

    expect(getCanonicalTemplateTaskType('minimax_h3_i2v'))
      .toBe('minimax_h3_i2v')
    expect(getCanonicalTemplateTaskType('minimax_h3_ref2v'))
      .toBe('minimax_h3_ref2v')
  })
})
