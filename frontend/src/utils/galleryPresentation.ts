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

  const translationKey = taskTypeId
    .replace('i2i_pro', 'face_swap')
    .replace('edit', 'custom_edit')
    .replace('img2img_lora', 'img2img')
    .replace('custom_video', 'img2video')
    .replace('video_lora', 'img2video')
    .replace('ltx_video', 'high_res_video')

  return t(`gallery.tabs.${translationKey}`)
}
