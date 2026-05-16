const VIDEO_THUMBNAIL_SOURCE_RE = /\.(mp4|mov|webm|mkv|avi)(?:\?.*)?$/i
const IMAGE_THUMBNAIL_RE = /(?:^|\/)(?:thumb|[^/]+_thumb)\.(?:webp|png|jpe?g)(?:\?.*)?$/i

export const normalizeGalleryThumbnailPath = (
  thumbnailPath: string,
  isVideo: boolean
): string => {
  if (!thumbnailPath) {
    return ''
  }

  const lastDotIndex = thumbnailPath.lastIndexOf('.')
  if (lastDotIndex <= thumbnailPath.lastIndexOf('/')) {
    return thumbnailPath
  }

  if (isVideo && VIDEO_THUMBNAIL_SOURCE_RE.test(thumbnailPath)) {
    return `${thumbnailPath.slice(0, lastDotIndex)}_thumb.jpg`
  }

  if (!isVideo && !IMAGE_THUMBNAIL_RE.test(thumbnailPath)) {
    return `${thumbnailPath.slice(0, lastDotIndex)}_thumb.webp`
  }

  return thumbnailPath
}
