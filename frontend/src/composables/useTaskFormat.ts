import dayjs from 'dayjs'
import i18n from '@/i18n'
import { resolveMediaUrl } from '@/utils/mediaUrl'
import { resolveTaskTypeLabel } from '@/utils/taskTypePresentation'

export function useTaskFormat() {
  const t = (key: string) => String(i18n.global.t(key))
  const te = (key: string) => i18n.global.te(key)
  const formatDate = (dateStr: string) => {
    return dayjs(dateStr).format('YYYY-MM-DD HH:mm:ss')
  }

  const getTypeLabel = (type: string) => resolveTaskTypeLabel(type, t, te)

  const getFileUrl = (path: string) => {
    return resolveMediaUrl(path)
  }

  const isVideoFile = (path: string) => {
    if (!path) return false
    const lowerPath = path.toLowerCase()
    return lowerPath.endsWith('.mp4') || lowerPath.includes('.mp4?') ||
           lowerPath.endsWith('.mov') || lowerPath.includes('.mov?') ||
           lowerPath.endsWith('.webm') || lowerPath.includes('.webm?') ||
           lowerPath.endsWith('.mkv') || lowerPath.includes('.mkv?') ||
           lowerPath.endsWith('.avi') || lowerPath.includes('.avi?')
  }

  return {
    formatDate,
    getTypeLabel,
    getFileUrl,
    isVideoFile
  }
}
