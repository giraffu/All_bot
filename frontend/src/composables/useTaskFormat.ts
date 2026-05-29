import dayjs from 'dayjs'
import { buildStorageFileUrl } from '@/utils/storageUrl'

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
      'custom_video': '图生视频',
      'video_lora': '图生视频',
      'img2img_lora': '图生图(附加模型)',
      'ltx_video': '高级图生视频',
      'wan22_video_v2': '图生视频 v2',
      'template_contribute': '模板共建',
      'txt2img': '文生图'
    }
    return map[type] || type
  }

  const getFileUrl = (path: string) => {
    return buildStorageFileUrl(path)
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
