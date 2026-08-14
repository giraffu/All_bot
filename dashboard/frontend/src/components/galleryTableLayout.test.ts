import { describe, expect, it } from 'vitest'

import { getGalleryTableColumnWidths } from './galleryTableLayout'

describe('gallery content table responsive layout', () => {
  it('keeps the mobile action rail narrow enough to leave room for content preview', () => {
    expect(getGalleryTableColumnWidths(true)).toEqual({
      preview: 104,
      action: 112,
    })
  })

  it('preserves the existing roomy desktop actions', () => {
    expect(getGalleryTableColumnWidths(false)).toEqual({
      preview: 120,
      action: 320,
    })
  })
})
