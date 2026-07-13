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

export const copyTextWithFallback = async (text) => {
  if (!text) return false

  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch (error) {
      console.error('Clipboard API failed:', error)
    }
  }

  try {
    const textArea = document.createElement('textarea')
    textArea.value = text
    textArea.style.position = 'fixed'
    textArea.style.left = '-999999px'
    textArea.style.top = '-999999px'

    document.body.appendChild(textArea)
    textArea.focus()
    textArea.select()

    const successful = document.execCommand('copy')
    document.body.removeChild(textArea)
    return successful
  } catch (error) {
    console.error('Fallback copy failed:', error)
    return false
  }
}
