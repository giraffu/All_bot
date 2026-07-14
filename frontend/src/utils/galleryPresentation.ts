export function formatGalleryTag(
  tag: string,
  t: (key: string, params?: Record<string, unknown>) => string
) {
  const stitchedMatch = tag.match(/^task\.(wan22|ltx)_stitched_video:(\d+)$/)
  if (stitchedMatch) {
    return t(`task.${stitchedMatch[1]}_stitched_video`, {
      count: Number.parseInt(stitchedMatch[2], 10),
    })
  }
  const segmentMatch = tag.match(/^task\.(wan22|ltx)_segment:(\d+)$/)
  if (segmentMatch) {
    return t(`task.${segmentMatch[1]}_segment`, {
      count: Number.parseInt(segmentMatch[2], 10),
    })
  }
  if (tag.startsWith('#task.')) {
    const key = tag.substring(1)
    return '#' + t(key)
  }
  if (tag.startsWith('task.')) {
    return t(tag)
  }
  return tag
}

export function resolveGalleryTaskTypeLabel(
  taskTypeId: string,
  t: (key: string) => string
) {
  if (taskTypeId === 'all') {
    return t('gallery.tabs.all')
  }

  const translationKeyMap: Record<string, string> = {
    i2i_pro: 'face_swap',
    edit: 'custom_edit',
    edit_group: 'edit_group',
    free_edit_v3_group: 'free_edit_v3_group',
    free_edit_v2_group: 'free_edit_v3_group',
    pornmaster_flux2_edit_bf16: 'free_edit_v3_group',
    pornmaster_flux2_single_edit: 'free_edit_v3_group',
    pornmaster_flux2_multi_edit: 'free_edit_v3_group',
    img2img_lora: 'img2img',
    custom_video: 'img2video',
    video_lora: 'img2video',
    img2video_group: 'img2video_group',
    ltx_video: 'high_res_video',
    ltx_video_flf2v: 'high_res_video',
    scail2_action_transfer_long: 'scail2_action_transfer',
  }
  const translationKey = translationKeyMap[taskTypeId] || taskTypeId

  return t(`gallery.tabs.${translationKey}`)
}
