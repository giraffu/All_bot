import { describe, expect, it } from 'vitest'

import {
  GALLERY_EDIT_GROUP_TASK_TYPE,
  GALLERY_FREE_EDIT_V2_GROUP_TASK_TYPE,
  buildGalleryTaskTypeTabs,
  isGalleryGroupedTaskType,
} from '@/utils/galleryTaskTypeFilters'

describe('galleryTaskTypeFilters', () => {
  it('keeps free edit v2 in its own gallery group', () => {
    const tabs = buildGalleryTaskTypeTabs([
      { id: 'edit', name: '自由P图' },
      { id: 'img2img_lora', name: '图生图(附加模型)' },
      { id: 'pornmaster_flux2_single_edit', name: '自由P图 v2' },
      { id: 'pornmaster_flux2_multi_edit', name: '自由P图 v2' },
    ])

    expect(tabs.map(tab => tab.id)).toEqual([
      GALLERY_EDIT_GROUP_TASK_TYPE,
      GALLERY_FREE_EDIT_V2_GROUP_TASK_TYPE,
    ])
    expect(isGalleryGroupedTaskType(GALLERY_EDIT_GROUP_TASK_TYPE)).toBe(true)
    expect(isGalleryGroupedTaskType(GALLERY_FREE_EDIT_V2_GROUP_TASK_TYPE)).toBe(true)
  })

  it('deduplicates LTX execution alias into the high-res video tab', () => {
    const tabs = buildGalleryTaskTypeTabs([
      { id: 'ltx_video', name: '高级图生视频' },
      { id: 'ltx_video_flf2v', name: '高级图生视频' },
    ])

    expect(tabs.map(tab => tab.id)).toEqual(['ltx_video'])
  })
})
