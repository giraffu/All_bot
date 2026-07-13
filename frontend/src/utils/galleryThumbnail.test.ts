import { describe, expect, it } from 'vitest'
import { normalizeGalleryThumbnailPath } from './galleryThumbnail'

describe('normalizeGalleryThumbnailPath', () => {
  it('keeps existing image thumbnails unchanged', () => {
    expect(
      normalizeGalleryThumbnailPath('history/demo/thumb.webp', false)
    ).toBe('history/demo/thumb.webp')
    expect(
      normalizeGalleryThumbnailPath('history/demo/original_thumb.webp', false)
    ).toBe('history/demo/original_thumb.webp')
    expect(
      normalizeGalleryThumbnailPath('history/demo/thumb.jpg?v=1', false)
    ).toBe('history/demo/thumb.jpg?v=1')
  })

  it('converts non-thumbnail image paths to webp thumbnails', () => {
    expect(
      normalizeGalleryThumbnailPath('history/demo/original.png', false)
    ).toBe('history/demo/original_thumb.webp')
  })

  it('converts video file paths to jpg thumbnails', () => {
    expect(
      normalizeGalleryThumbnailPath('history/demo/original.mp4', true)
    ).toBe('history/demo/original_thumb.jpg')
  })
})
