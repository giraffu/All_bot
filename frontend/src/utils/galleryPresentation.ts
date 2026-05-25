export function formatGalleryTag(
  tag: string,
  t: (key: string) => string
) {
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
    img2img_lora: 'img2img',
    custom_video: 'img2video',
    video_lora: 'img2video',
    img2video_group: 'img2video_group',
    ltx_video: 'high_res_video',
  }
  const translationKey = translationKeyMap[taskTypeId] || taskTypeId

  return t(`gallery.tabs.${translationKey}`)
}
