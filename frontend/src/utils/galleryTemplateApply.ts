import type { GalleryPost } from '@/types/gallery'

export const GALLERY_TEMPLATE_APPLY_DISABLED_REASON_WAN22_STITCHED = 'wan22_stitched'
export const GALLERY_TEMPLATE_APPLY_DISABLED_REASON_MISSING_SCAIL2_MOTION_VIDEO = 'missing_scail2_motion_video'
export const GALLERY_TEMPLATE_APPLY_DISABLED_REASON_I2I_DRAW_DISABLED = 'i2i_draw_disabled'
export const GALLERY_TEMPLATE_APPLY_DISABLED_REASON_PROMPT_UNLOCK_REQUIRED = 'gallery_prompt_unlock_required'

export const resolveGalleryTemplateApplyDisabledReason = (
  post: GalleryPost | null | undefined
): string | null => {
  if (!post) {
    return null
  }

  if (post.task_type === 'i2i_draw') {
    return GALLERY_TEMPLATE_APPLY_DISABLED_REASON_I2I_DRAW_DISABLED
  }

  if (post.template_apply_supported === false) {
    return post.template_apply_disabled_reason
      || (post.result_meta?.wan22_is_stitched
        ? GALLERY_TEMPLATE_APPLY_DISABLED_REASON_WAN22_STITCHED
        : 'unsupported')
  }

  if (post.result_meta?.wan22_is_stitched) {
    return GALLERY_TEMPLATE_APPLY_DISABLED_REASON_WAN22_STITCHED
  }

  if (post.prompt_is_masked === true) {
    return GALLERY_TEMPLATE_APPLY_DISABLED_REASON_PROMPT_UNLOCK_REQUIRED
  }

  if (post.template_apply_supported === true) {
    return null
  }

  return post.result_meta?.wan22_is_stitched
    ? GALLERY_TEMPLATE_APPLY_DISABLED_REASON_WAN22_STITCHED
    : null
}

export const isGalleryTemplateApplySupported = (
  post: GalleryPost | null | undefined
): boolean => resolveGalleryTemplateApplyDisabledReason(post) === null

export const resolveGalleryTemplateApplyDisabledMessage = (
  t: (key: string) => string,
  reason: string | null | undefined
): string => {
  if (reason === GALLERY_TEMPLATE_APPLY_DISABLED_REASON_WAN22_STITCHED) {
    return t('template_apply.disabled.wan22_stitched')
  }
  if (reason === GALLERY_TEMPLATE_APPLY_DISABLED_REASON_MISSING_SCAIL2_MOTION_VIDEO) {
    return t('template_apply.disabled.missing_scail2_motion_video')
  }
  if (reason === GALLERY_TEMPLATE_APPLY_DISABLED_REASON_I2I_DRAW_DISABLED) {
    return t('template_apply.disabled.i2i_draw_disabled')
  }
  if (reason === GALLERY_TEMPLATE_APPLY_DISABLED_REASON_PROMPT_UNLOCK_REQUIRED) {
    return t('template_apply.disabled.gallery_prompt_unlock_required')
  }
  return t('template_apply.disabled.unsupported')
}
