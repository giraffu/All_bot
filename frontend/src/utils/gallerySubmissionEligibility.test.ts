import { describe, expect, it } from 'vitest'
import { isGallerySubmissionEligible } from '@/utils/gallerySubmissionEligibility'

describe('isGallerySubmissionEligible', () => {
  it.each([
    ['minimax_h3_i2v', true],
    ['minimax_h3_flf2v', true],
    ['minimax_h3_t2v', false],
    ['minimax_h3_ref2v', false],
  ])('limits MiniMax H3 contribution to image modes', (type, expected) => {
    expect(isGallerySubmissionEligible({ type, allow_contribute: true })).toBe(expected)
  })

  it('rejects template-derived records even for supported types', () => {
    expect(isGallerySubmissionEligible({
      type: 'minimax_h3_i2v', allow_contribute: false,
    })).toBe(false)
  })
})
