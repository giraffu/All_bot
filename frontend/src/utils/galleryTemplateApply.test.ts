import { describe, expect, it } from 'vitest'

import {
  resolveGalleryTemplateApplyDisabledMessage,
  resolveGalleryTemplateApplyDisabledReason,
} from '@/utils/galleryTemplateApply'

describe('galleryTemplateApply', () => {
  it('disables i2i draw template apply even when older payloads omit support flags', () => {
    const reason = resolveGalleryTemplateApplyDisabledReason({
      task_type: 'i2i_draw',
      template_apply_supported: true,
    } as any)

    expect(reason).toBe('i2i_draw_disabled')
    expect(resolveGalleryTemplateApplyDisabledMessage(key => key, reason))
      .toBe('template_apply.disabled.i2i_draw_disabled')
  })
})
