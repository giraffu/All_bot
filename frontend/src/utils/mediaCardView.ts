import { normalizeGalleryThumbnailPath } from '@/utils/galleryThumbnail'
import { getFileUrl, isVideoFile } from '@/utils/mediaFiles'

export interface MediaCardLike {
  id: number | string
  thumbnail_url?: string
  media_url?: string
  media_type: string
}

export interface MediaCardViewOptions {
  fallbackToOriginalWithoutThumbnail?: boolean
  normalizeGalleryThumbnail?: boolean
}

export interface MediaCardView {
  isVideo: boolean
  initialSrc: string
  originalSrc: string
  posterSrc: string
}

export interface MediaDetailView {
  isVideo: boolean
  mediaSrc: string
  posterSrc: string
}

export function isMediaCardVideo(post: MediaCardLike): boolean {
  return isVideoFile(post.media_url || post.thumbnail_url || '', post.media_type)
}

export function resolveMediaCardOriginalSrc(post: MediaCardLike): string {
  if (!post.media_url) {
    return ''
  }

  return post.media_url.includes('X-Amz-Signature')
    ? post.media_url
    : getFileUrl(post.media_url, post.id)
}

export function resolveMediaCardThumbnailSrc(
  post: MediaCardLike,
  options: MediaCardViewOptions = {}
): string {
  if (!post.thumbnail_url) {
    return ''
  }

  const thumbnailPath = options.normalizeGalleryThumbnail
    ? normalizeGalleryThumbnailPath(post.thumbnail_url, isMediaCardVideo(post))
    : post.thumbnail_url

  return getFileUrl(thumbnailPath, post.id)
}

export function resolveMediaCardInitialSrc(
  post: MediaCardLike,
  options: MediaCardViewOptions = {}
): string {
  const thumbnailSrc = resolveMediaCardThumbnailSrc(post, options)
  if (thumbnailSrc) {
    return thumbnailSrc
  }

  if (
    options.fallbackToOriginalWithoutThumbnail
    && post.media_url
    && !isMediaCardVideo(post)
  ) {
    return resolveMediaCardOriginalSrc(post)
  }

  return ''
}

export function resolveMediaCardPosterSrc(
  post: MediaCardLike,
  options: MediaCardViewOptions = {}
): string {
  return resolveMediaCardThumbnailSrc(post, options)
}

export function resolveMediaCardView(
  post: MediaCardLike,
  options: MediaCardViewOptions = {}
): MediaCardView {
  return {
    isVideo: isMediaCardVideo(post),
    initialSrc: resolveMediaCardInitialSrc(post, options),
    originalSrc: resolveMediaCardOriginalSrc(post),
    posterSrc: resolveMediaCardPosterSrc(post, options),
  }
}

export function resolveMediaDetailView(
  post: MediaCardLike,
  options: MediaCardViewOptions = {}
): MediaDetailView {
  return {
    isVideo: isMediaCardVideo(post),
    mediaSrc: resolveMediaCardOriginalSrc(post),
    posterSrc: resolveMediaCardPosterSrc(post, options),
  }
}
