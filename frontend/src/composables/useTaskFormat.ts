import dayjs from 'dayjs'

export function useTaskFormat() {
  const formatDate = (dateStr: string) => {
    return dayjs(dateStr).format('YYYY-MM-DD HH:mm:ss')
  }

  const getTypeLabel = (type: string) => {
    const map: Record<string, string> = {
      'image': '自由P图',
      'edit': '自由P图',
      'i2i_pro': '幻想换脸',
      'i2i_draw': '局部重绘',
      'undress': '快速脱衣',
      'masturbation': '快速自慰',
      'face_swap': '快速换脸',
      'face_swap_step1': '快速换脸',
      'face_swap_step2': '快速换脸',
      'face_video': '视频换脸',
      'face_video_step1': '视频换脸',
      'face_video_step2': '视频换脸',
      'random_faceswap': '随机换脸',
      'penetration_step1': '快速抽插',
      'penetration_step2': '快速抽插',
      'perfect_video_insert': '动图传教士',
      'doggy_style': '动图后入',
      'blowjob': '口交黑人',
      'undress_tongue': '脱衣吐舌',
      'closeup_blowjob': '特写口交',
      'custom_video': '自定义图生视频',
      'video_lora': '图生视频(附加模型)',
      'img2img_lora': '图生图(附加模型)',
      'ltx_video': '高级图生视频',
      'template_contribute': '模板共建',
      'txt2img': '文生图'
    }
    return map[type] || type
  }

  const getFileUrl = (path: string) => {
    if (!path) return ''
    if (path.startsWith('http')) return path
    
    const storageUrl = import.meta.env.VITE_STORAGE_URL || ''
    const base = storageUrl.endsWith('/') ? storageUrl.slice(0, -1) : storageUrl
    
    if (!path.startsWith('bot-data/') && !path.startsWith('comfyui-temp/')) {
      if (!path.includes('/')) {
        return `${base}/comfyui-temp/${path}`
      }
      return `${base}/bot-data/${path}`
    }
    return `${base}/${path}`
  }

  const isVideoFile = (path: string) => {
    if (!path) return false
    const lowerPath = path.toLowerCase()
    return lowerPath.endsWith('.mp4') || 
           lowerPath.endsWith('.mov') || 
           lowerPath.endsWith('.webm') || 
           lowerPath.endsWith('.mkv') ||
           lowerPath.endsWith('.avi')
  }

  return {
    formatDate,
    getTypeLabel,
    getFileUrl,
    isVideoFile
  }
}
