import { describe, expect, it } from 'vitest'
import { resolveMediaCardView, resolveMediaDetailView } from './mediaCardView'

describe('resolveMediaCardView', () => {
  it('normalizes gallery image thumbnails when requested', () => {
    const view = resolveMediaCardView(
      {
        id: 7,
        thumbnail_url: 'https://r2.example/history/demo/original.png',
        media_url: 'https://r2.example/history/demo/original.png',
        media_type: 'image',
      },
      { normalizeGalleryThumbnail: true }
    )

    expect(view.isVideo).toBe(false)
    expect(view.initialSrc).toBe('https://r2.example/history/demo/original_thumb.webp?v=7')
    expect(view.posterSrc).toBe('https://r2.example/history/demo/original_thumb.webp?v=7')
  })

  it('normalizes gallery video thumbnails to poster images', () => {
    const view = resolveMediaCardView(
      {
        id: 8,
        thumbnail_url: 'https://r2.example/history/demo/original.mp4',
        media_url: 'https://r2.example/history/demo/original.mp4',
        media_type: 'video',
      },
      { normalizeGalleryThumbnail: true }
    )

    expect(view.isVideo).toBe(true)
    expect(view.initialSrc).toBe('https://r2.example/history/demo/original_thumb.jpg?v=8')
    expect(view.posterSrc).toBe('https://r2.example/history/demo/original_thumb.jpg?v=8')
  })

  it('falls back to original images when thumbnails are missing and the page allows it', () => {
    const view = resolveMediaCardView(
      {
        id: 9,
        thumbnail_url: '',
        media_url: 'https://r2.example/history/demo/original.png',
        media_type: 'image',
      },
      { fallbackToOriginalWithoutThumbnail: true }
    )

    expect(view.isVideo).toBe(false)
    expect(view.initialSrc).toBe('https://r2.example/history/demo/original.png?v=9')
    expect(view.posterSrc).toBe('')
  })

  it('builds detail media view for images without poster', () => {
    const view = resolveMediaDetailView({
      id: 10,
      thumbnail_url: 'https://r2.example/history/demo/original_thumb.webp',
      media_url: 'https://r2.example/history/demo/original.png',
      media_type: 'image',
    })

    expect(view.isVideo).toBe(false)
    expect(view.mediaSrc).toBe('https://r2.example/history/demo/original.png?v=10')
    expect(view.posterSrc).toBe('https://r2.example/history/demo/original_thumb.webp?v=10')
  })

  it('builds detail media view for videos with normalized gallery poster', () => {
    const view = resolveMediaDetailView(
      {
        id: 11,
        thumbnail_url: 'https://r2.example/history/demo/original.mp4',
        media_url: 'https://r2.example/history/demo/original.mp4',
        media_type: 'video',
      },
      { normalizeGalleryThumbnail: true }
    )

    expect(view.isVideo).toBe(true)
    expect(view.mediaSrc).toBe('https://r2.example/history/demo/original.mp4?v=11')
    expect(view.posterSrc).toBe('https://r2.example/history/demo/original_thumb.jpg?v=11')
  })
})
