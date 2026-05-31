import { describe, expect, it } from 'vitest'

import { formatGalleryTag, resolveGalleryTaskTypeLabel } from '@/utils/galleryPresentation'

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

describe('formatGalleryTag', () => {
  it('formats wan22 single frame tag with translation', () => {
    const t = (key: string) => (key === 'task.wan22_start_frame' ? '首图生成' : key)

    expect(formatGalleryTag('task.wan22_start_frame', t)).toBe('首图生成')
  })

  it('formats wan22 start/end frame tag with translation', () => {
    const t = (key: string) => (key === 'task.wan22_start_end_frame' ? '首尾帧生成' : key)

    expect(formatGalleryTag('task.wan22_start_end_frame', t)).toBe('首尾帧生成')
  })

  it('formats stitched wan22 tag with segment count', () => {
    const t = (key: string, params?: Record<string, unknown>) =>
      key === 'task.wan22_stitched_video'
        ? `拼接视频-${params?.count as number}`
        : key

    expect(formatGalleryTag('task.wan22_stitched_video:2', t)).toBe('拼接视频-2')
    expect(formatGalleryTag('task.wan22_stitched_video:3', t)).toBe('拼接视频-3')
  })
})
