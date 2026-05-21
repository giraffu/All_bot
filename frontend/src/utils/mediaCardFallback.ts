import {
  isMediaCardVideo,
  resolveMediaCardInitialSrc,
  resolveMediaCardOriginalSrc,
  type MediaCardLike,
  type MediaCardViewOptions,
} from '@/utils/mediaCardView'

interface MediaCardFallbackOptions extends MediaCardViewOptions {
  requireThumbnailForOriginalFallback?: boolean
}

export { resolveMediaCardInitialSrc, resolveMediaCardOriginalSrc }

export function handleMediaCardImageError(
  event: Event,
  post: MediaCardLike,
  options: MediaCardFallbackOptions = {}
) {
  const img = event.target as HTMLImageElement
  const canFallbackToOriginalImage = !!post.media_url
    && !isMediaCardVideo(post)
    && (
      !options.requireThumbnailForOriginalFallback
      || !!post.thumbnail_url
    )

  if (!img.dataset.fallbackAttempted && canFallbackToOriginalImage) {
    img.dataset.fallbackAttempted = 'true'
    img.src = resolveMediaCardOriginalSrc(post)
    img.style.opacity = '1'
    return
  }

  img.style.opacity = '0.3'
}
