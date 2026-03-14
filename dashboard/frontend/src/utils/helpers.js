import { apiBaseUrl } from '../api/api'

export const getFileUrl = (userId, type, filename) => {
  if (!filename) return ''
  const userIdStr = String(userId)
  const basename = filename.split(/[\\/]/).pop()
  return `${apiBaseUrl}/images/${userIdStr}/${type}/${basename}`
}

export const isVideo = (filename) => {
  if (!filename) return false
  const ext = filename.split('.').pop().toLowerCase()
  return ['mp4', 'webm', 'ogg', 'mov'].includes(ext)
}

export const formatDate = (dateString) => {
  if (!dateString) return 'n/a'
  return new Date(dateString).toLocaleString()
}
