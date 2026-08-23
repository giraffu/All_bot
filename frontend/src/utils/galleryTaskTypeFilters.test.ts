// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from 'vitest'

import {
  GALLERY_EDIT_GROUP_TASK_TYPE,
  GALLERY_FREE_EDIT_V2_5_GROUP_TASK_TYPE,
  GALLERY_FREE_EDIT_V3_GROUP_TASK_TYPE,
  buildGalleryTaskTypeTabs,
  filterVisibleGalleryTaskTypes,
  isGalleryGroupedTaskType,
} from '@/utils/galleryTaskTypeFilters'

describe('galleryTaskTypeFilters', () => {
  beforeEach(() => {
    window.__ALLBOT_CONFIG__ = {
      enable_ltx_video: true,
      enable_minimax_h3: true,
      enable_minimax_h3_entry: false,
      enable_gallery_minimax_h3_entry: false,
    }
  })

  it('uses the market switch independently from the Web Pro workbench switch', () => {
    window.__ALLBOT_CONFIG__ = {
      enable_minimax_h3: true,
      enable_minimax_h3_entry: false,
      enable_gallery_minimax_h3_entry: true,
    }

    expect(filterVisibleGalleryTaskTypes([
      { id: 'minimax_h3_i2v', name: '高级图生视频pro' },
    ])).toEqual([
      { id: 'minimax_h3_i2v', name: '高级图生视频pro' },
    ])
  })
  it('groups new and historical free edits under v3', () => {
    const tabs = buildGalleryTaskTypeTabs([
      { id: 'edit', name: '自由P图' },
      { id: 'img2img_lora', name: '图生图(附加模型)' },
      { id: 'pornmaster_flux2_edit_bf16', name: '自由P图 v3' },
      { id: 'pornmaster_flux2_single_edit', name: '自由P图 v3' },
      { id: 'pornmaster_flux2_multi_edit', name: '自由P图 v3' },
    ])

    expect(tabs.map(tab => tab.id)).toEqual([
      GALLERY_EDIT_GROUP_TASK_TYPE,
      GALLERY_FREE_EDIT_V3_GROUP_TASK_TYPE,
    ])
    expect(isGalleryGroupedTaskType(GALLERY_EDIT_GROUP_TASK_TYPE)).toBe(true)
    expect(isGalleryGroupedTaskType(GALLERY_FREE_EDIT_V3_GROUP_TASK_TYPE)).toBe(true)
  })

  it('keeps free edit v2.5 in its own gallery group', () => {
    const tabs = buildGalleryTaskTypeTabs([
      { id: 'free_edit_v2_5', name: '自由P图 v2.5' },
      { id: 'pornmaster_flux2_edit_bf16', name: '自由P图 v3' },
    ])

    expect(tabs.map(tab => tab.id)).toEqual([
      GALLERY_FREE_EDIT_V2_5_GROUP_TASK_TYPE,
      GALLERY_FREE_EDIT_V3_GROUP_TASK_TYPE,
    ])
    expect(isGalleryGroupedTaskType(GALLERY_FREE_EDIT_V2_5_GROUP_TASK_TYPE)).toBe(true)
  })

  it('deduplicates LTX execution alias into the high-res video tab', () => {
    const tabs = buildGalleryTaskTypeTabs([
      { id: 'ltx_video', name: '高级图生视频' },
      { id: 'ltx_video_flf2v', name: '高级图生视频' },
    ])

    expect(tabs.map(tab => tab.id)).toEqual(['ltx_video'])
  })

  it('groups MiniMax H3 image modes under one Pro tab', () => {
    const tabs = buildGalleryTaskTypeTabs([
      { id: 'minimax_h3_i2v', name: '高级图生视频pro · 图生视频' },
      { id: 'minimax_h3_flf2v', name: '高级图生视频pro · 首尾帧' },
    ])

    expect(tabs.map(tab => tab.id)).toEqual(['minimax_h3'])
    expect(isGalleryGroupedTaskType('minimax_h3')).toBe(true)
  })

  it('hides H3 Pro from the market when only its ordinary entry is disabled', () => {
    const visibleTypes = filterVisibleGalleryTaskTypes([
      { id: 'i2i_pro', name: '图片生成' },
      { id: 'i2i_draw', name: '局部重绘' },
      { id: 'edit', name: '自由P图' },
      { id: 'ltx_video', name: '高级图生视频' },
      { id: 'minimax_h3_i2v', name: '高级图生视频pro' },
    ])

    expect(visibleTypes.map(type => type.id)).toEqual([
      'i2i_pro', 'edit', 'ltx_video',
    ])
  })
})
