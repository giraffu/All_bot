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

  let url = path
  if (!path.startsWith('http')) {
    const storageUrl = import.meta.env.VITE_STORAGE_URL || ''
    const base = storageUrl.endsWith('/') ? storageUrl.slice(0, -1) : storageUrl

    if (!path.startsWith('bot-data/') && !path.startsWith('comfyui-temp/')) {
      url = !path.includes('/')
        ? `${base}/comfyui-temp/${path}`
        : `${base}/bot-data/${path}`
    } else {
      url = `${base}/${path}`
    }
  }

  if (!postId || url.includes('X-Amz-Signature') || /[?&]v=/.test(url)) {
    return url
  }

  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}v=${postId}`
}
