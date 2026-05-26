import { describe, expect, it } from 'vitest'

import { resolveGalleryTaskTypeLabel } from '@/utils/galleryPresentation'

describe('resolveGalleryTaskTypeLabel', () => {
  it('returns translated txt2img label', () => {
    const t = (key: string) => {
      if (key === 'gallery.tabs.txt2img') {
        return '文生图'
      }
      return key
    }

    expect(resolveGalleryTaskTypeLabel('txt2img', t)).toBe('文生图')
  })
})
