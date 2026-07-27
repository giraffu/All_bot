import { resolveMediaUrl } from '@/utils/mediaUrl'

export const isVideoFile = (path: string, mediaType?: string): boolean => {
  if (mediaType) {
    return mediaType === 'video'
  }
  if (!path) {
    return false
  }

  const lowerPath = path.toLowerCase()
  return (
    lowerPath.endsWith('.mp4') ||
    lowerPath.includes('.mp4?') ||
    lowerPath.endsWith('.mov') ||
    lowerPath.includes('.mov?') ||
    lowerPath.endsWith('.webm') ||
    lowerPath.includes('.webm?') ||
    lowerPath.endsWith('.mkv') ||
    lowerPath.includes('.mkv?') ||
    lowerPath.endsWith('.avi') ||
    lowerPath.includes('.avi?')
  )
}

export const getFileUrl = (path: string, postId?: number | string): string => {
  if (!path) {
    return ''
  }

  const url = resolveMediaUrl(path)
  if (!url) {
    return ''
  }

  if (!postId || url.includes('X-Amz-Signature') || /[?&]v=/.test(url)) {
    return url
  }

  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}v=${postId}`
}
