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

  it('disables template apply while the server marks the prompt as masked', () => {
    window.__ALLBOT_CONFIG__ = { enable_minimax_h3: true }
    const reason = resolveGalleryTemplateApplyDisabledReason({
      task_type: 'minimax_h3_i2v',
      template_apply_supported: true,
      prompt_unlocked: false,
      prompt_unlockable: true,
      prompt_is_masked: true,
    } as any)

    expect(reason).toBe('gallery_prompt_unlock_required')
    expect(resolveGalleryTemplateApplyDisabledMessage(key => key, reason))
      .toBe('template_apply.disabled.gallery_prompt_unlock_required')
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
})
