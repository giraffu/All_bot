import { describe, expect, it } from 'vitest'

import i18n from '@/i18n'
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

  it('returns translated free edit v2 group label', () => {
    const t = (key: string) => {
      if (key === 'gallery.tabs.free_edit_v2_group') {
        return '自由P图 v2'
      }
      return key
    }

    expect(resolveGalleryTaskTypeLabel('free_edit_v2_group', t)).toBe('自由P图 v2')
  })

  it('maps raw free edit v2 task types to the shared gallery label', () => {
    i18n.global.locale.value = 'zh'
    const t = (key: string) => String(i18n.global.t(key))

    expect(resolveGalleryTaskTypeLabel('pornmaster_flux2_single_edit', t)).toBe('自由P图 v2')
    expect(resolveGalleryTaskTypeLabel('pornmaster_flux2_multi_edit', t)).toBe('自由P图 v2')
  })

  it('returns translated scail2 labels from the shared locale', () => {
    i18n.global.locale.value = 'zh'
    const t = (key: string) => String(i18n.global.t(key))

    expect(resolveGalleryTaskTypeLabel('scail2_action_transfer', t)).toBe('动作迁移')
    expect(resolveGalleryTaskTypeLabel('scail2_action_transfer_long', t)).toBe('动作迁移')
    expect(resolveGalleryTaskTypeLabel('scail2_video_replacement', t)).toBe('视频换人')
    expect(resolveGalleryTaskTypeLabel('scail2_face_swap_v2', t)).toBe('视频换脸')
  })

  it('maps LTX FLF2V execution alias to the shared high-res video label', () => {
    i18n.global.locale.value = 'zh'
    const t = (key: string) => String(i18n.global.t(key))

    expect(resolveGalleryTaskTypeLabel('ltx_video_flf2v', t)).toBe('高级图生视频')
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

  it('formats wan22 segment tag with segment index', () => {
    const t = (key: string, params?: Record<string, unknown>) =>
      key === 'task.wan22_segment'
        ? `第${params?.count as number}段`
        : key

    expect(formatGalleryTag('task.wan22_segment:1', t)).toBe('第1段')
    expect(formatGalleryTag('task.wan22_segment:4', t)).toBe('第4段')
  })

  it('formats ltx frame and chain tags with translation', () => {
    const t = (key: string, params?: Record<string, unknown>) => {
      if (key === 'task.ltx_start_end_frame') return 'LTX 首尾帧'
      if (key === 'task.ltx_segment') return `LTX 第${params?.count as number}段`
      if (key === 'task.ltx_stitched_video') return `LTX 拼接-${params?.count as number}`
      return key
    }

    expect(formatGalleryTag('task.ltx_start_end_frame', t)).toBe('LTX 首尾帧')
    expect(formatGalleryTag('task.ltx_segment:2', t)).toBe('LTX 第2段')
    expect(formatGalleryTag('task.ltx_stitched_video:3', t)).toBe('LTX 拼接-3')
  })
})
