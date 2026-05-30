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

  it('returns translated wan22 video v2 label', () => {
    const t = (key: string) => {
      if (key === 'gallery.tabs.wan22_video_v2') {
        return '图生视频 v2'
      }
      return key
    }

    expect(resolveGalleryTaskTypeLabel('wan22_video_v2', t)).toBe('图生视频 v2')
  })
})
