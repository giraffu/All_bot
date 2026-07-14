import { describe, expect, it } from 'vitest'

import {
  GALLERY_EDIT_GROUP_TASK_TYPE,
  GALLERY_FREE_EDIT_V3_GROUP_TASK_TYPE,
  buildGalleryTaskTypeTabs,
  filterVisibleGalleryTaskTypes,
  isGalleryGroupedTaskType,
} from '@/utils/galleryTaskTypeFilters'

describe('galleryTaskTypeFilters', () => {
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

  it('deduplicates LTX execution alias into the high-res video tab', () => {
    const tabs = buildGalleryTaskTypeTabs([
      { id: 'ltx_video', name: '高级图生视频' },
      { id: 'ltx_video_flf2v', name: '高级图生视频' },
    ])

    expect(tabs.map(tab => tab.id)).toEqual(['ltx_video'])
  })

  it('hides disabled Web gallery task types from config consumers', () => {
    const visibleTypes = filterVisibleGalleryTaskTypes([
      { id: 'i2i_pro', name: '图片生成' },
      { id: 'i2i_draw', name: '局部重绘' },
      { id: 'edit', name: '自由P图' },
    ])

    expect(visibleTypes.map(type => type.id)).toEqual(['i2i_pro', 'edit'])
  })
})
