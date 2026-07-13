import { getRuntimeConfig } from '@/config/runtime'

export const buildStorageFileUrl = (path: string): string => {
  if (!path) {
    return ''
  }

  if (path.startsWith('http')) {
    return path
  }

  const storageUrl = getRuntimeConfig('storage_url', '')
  const base = storageUrl.endsWith('/') ? storageUrl.slice(0, -1) : storageUrl

  if (!path.startsWith('bot-data/') && !path.startsWith('comfyui-temp/')) {
    if (!path.includes('/')) {
      return `${base}/comfyui-temp/${path}`
    }
    return `${base}/bot-data/${path}`
  }

  return `${base}/${path}`
}
