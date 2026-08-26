import type { GalleryTaskTypeOption } from '@/composables/useGalleryConfig'
import {
  isGalleryTaskTypeEntryEnabled,
} from '@/config/generationFeatureAvailability'

export const GALLERY_EDIT_GROUP_TASK_TYPE = 'edit_group'
export const GALLERY_FREE_EDIT_V3_GROUP_TASK_TYPE = 'free_edit_v3_group'
export const GALLERY_FREE_EDIT_V2_5_GROUP_TASK_TYPE = 'free_edit_v2_5_group'
export const GALLERY_FREE_EDIT_V2_GROUP_TASK_TYPE = 'free_edit_v2_group'
export const GALLERY_IMG2VIDEO_GROUP_TASK_TYPE = 'img2video_group'
export const GALLERY_LORA_MODEL_NONE = '__none__'
export const GALLERY_MINIMAX_H3_GROUP_TASK_TYPE = 'minimax_h3'

const WEB_DISABLED_GALLERY_TASK_TYPES = new Set(['i2i_draw'])

const GALLERY_GROUPED_TASK_TYPE_ALIASES: Record<string, string> = {
  edit: GALLERY_EDIT_GROUP_TASK_TYPE,
  img2img_lora: GALLERY_EDIT_GROUP_TASK_TYPE,
  free_edit_v2_5: GALLERY_FREE_EDIT_V2_5_GROUP_TASK_TYPE,
  pornmaster_flux2_edit_bf16: GALLERY_FREE_EDIT_V3_GROUP_TASK_TYPE,
  pornmaster_flux2_single_edit: GALLERY_FREE_EDIT_V3_GROUP_TASK_TYPE,
  pornmaster_flux2_multi_edit: GALLERY_FREE_EDIT_V3_GROUP_TASK_TYPE,
  custom_video: GALLERY_IMG2VIDEO_GROUP_TASK_TYPE,
  video_lora: GALLERY_IMG2VIDEO_GROUP_TASK_TYPE,
  ltx_video_flf2v: 'ltx_video',
  scail2_action_transfer_long: 'scail2_action_transfer',
  minimax_h3_i2v: GALLERY_MINIMAX_H3_GROUP_TASK_TYPE,
  minimax_h3_flf2v: GALLERY_MINIMAX_H3_GROUP_TASK_TYPE,
  minimax_h3_ref2v: GALLERY_MINIMAX_H3_GROUP_TASK_TYPE,
}

export function isGalleryGroupedTaskType(taskType: string): boolean {
  return (
    taskType === GALLERY_EDIT_GROUP_TASK_TYPE
    || taskType === GALLERY_FREE_EDIT_V2_5_GROUP_TASK_TYPE
    || taskType === GALLERY_FREE_EDIT_V3_GROUP_TASK_TYPE
    || taskType === GALLERY_FREE_EDIT_V2_GROUP_TASK_TYPE
    || taskType === GALLERY_IMG2VIDEO_GROUP_TASK_TYPE
    || taskType === GALLERY_MINIMAX_H3_GROUP_TASK_TYPE
  )
}

export function filterVisibleGalleryTaskTypes(
  allowedTypes: GalleryTaskTypeOption[]
): GalleryTaskTypeOption[] {
  return allowedTypes.filter((taskType) => (
    Boolean(taskType?.id)
    && !WEB_DISABLED_GALLERY_TASK_TYPES.has(taskType.id)
    && isGalleryTaskTypeEntryEnabled(taskType.id)
  ))
}

export function buildGalleryTaskTypeTabs(
  allowedTypes: GalleryTaskTypeOption[]
): GalleryTaskTypeOption[] {
  const dedupedTabs: GalleryTaskTypeOption[] = []
  const seen = new Set<string>()

  allowedTypes.forEach((taskType) => {
    const normalizedId = GALLERY_GROUPED_TASK_TYPE_ALIASES[taskType.id] || taskType.id
    if (seen.has(normalizedId)) {
      return
    }
    seen.add(normalizedId)
    dedupedTabs.push({
      ...taskType,
      id: normalizedId,
    })
  })

  return dedupedTabs
}
