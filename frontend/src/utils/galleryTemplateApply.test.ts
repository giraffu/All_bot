// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from 'vitest'

import {
  resolveGalleryTemplateApplyDisabledMessage,
  resolveGalleryTemplateApplyDisabledReason,
} from '@/utils/galleryTemplateApply'

describe('galleryTemplateApply', () => {
  beforeEach(() => {
    window.__ALLBOT_CONFIG__ = {
      enable_ltx_video: true,
      enable_minimax_h3: false,
    }
  })

  it('keeps LTX apply open and disables H3 Pro apply in prod', () => {
    expect(resolveGalleryTemplateApplyDisabledReason({
      task_type: 'ltx_video',
      template_apply_supported: true,
    } as any)).toBeNull()
    expect(resolveGalleryTemplateApplyDisabledReason({
      task_type: 'minimax_h3_i2v',
      template_apply_supported: true,
    } as any)).toBe('feature_disabled')
  })
  it('disables i2i draw template apply even when older payloads omit support flags', () => {
    const reason = resolveGalleryTemplateApplyDisabledReason({
      task_type: 'i2i_draw',
      template_apply_supported: true,
    } as any)

    expect(reason).toBe('i2i_draw_disabled')
    expect(resolveGalleryTemplateApplyDisabledMessage(key => key, reason))
      .toBe('template_apply.disabled.i2i_draw_disabled')
  })

  it('keeps template apply available while the public prompt is masked', () => {
    window.__ALLBOT_CONFIG__ = { enable_minimax_h3: true }
    const reason = resolveGalleryTemplateApplyDisabledReason({
      task_type: 'minimax_h3_i2v',
      template_apply_supported: true,
      prompt_unlocked: false,
      prompt_unlockable: true,
      prompt_is_masked: true,
    } as any)

    expect(reason).toBeNull()
  })

  it('keeps template apply enabled for authors and users who unlocked the prompt', () => {
    window.__ALLBOT_CONFIG__ = { enable_minimax_h3: true }
    for (const post of [
      { prompt_unlocked: true, prompt_is_masked: false },
      { prompt_unlocked: undefined, prompt_is_masked: undefined },
    ]) {
      expect(resolveGalleryTemplateApplyDisabledReason({
        task_type: 'minimax_h3_i2v',
        template_apply_supported: true,
        ...post,
      } as any)).toBeNull()
    }
  })

  it('uses the dedicated disabled reason for stitched H3 chains', () => {
    window.__ALLBOT_CONFIG__ = { enable_minimax_h3: true }
    const reason = resolveGalleryTemplateApplyDisabledReason({
      task_type: 'minimax_h3_i2v',
      template_apply_supported: false,
      template_apply_disabled_reason: 'minimax_h3_stitched',
      result_meta: { minimax_h3_is_stitched: true },
    } as any)

    expect(reason).toBe('minimax_h3_stitched')
    expect(resolveGalleryTemplateApplyDisabledMessage(key => key, reason))
      .toBe('template_apply.disabled.minimax_h3_stitched')
  })
})
