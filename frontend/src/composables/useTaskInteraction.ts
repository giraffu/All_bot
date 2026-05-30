import { ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import api from '@/api'
import dayjs from 'dayjs'
import { useTaskFormat } from './useTaskFormat'

export const resolveTaskDownloadUrl = (
  record: { output_file?: string; output_file_url?: string },
  getFileUrl: (path: string) => string
) => {
  if (record.output_file_url) {
    return record.output_file_url
  }
  if (!record.output_file) {
    return ''
  }
  return getFileUrl(record.output_file)
}

export function useTaskInteraction(options?: {
  onDeleteSuccess?: (record: any) => void
}) {
  const submittingTasks = ref<Record<string, boolean>>({})
  const { getFileUrl, isVideoFile } = useTaskFormat()

  const submitToGallery = async (record: any) => {
    if (submittingTasks.value[record.task_id]) return
    submittingTasks.value[record.task_id] = true
    
    try {
      const payload = {
        width: record.width || null,
        height: record.height || null,
        duration: record.duration || null
      }
      
      const res = await api.post(`/gallery/posts/submit/${record.task_id}`, payload)
      message.success(res.data?.message || '投稿成功！')
      record.is_public = true
    } catch (error: any) {
      console.error(error)
      if (error.response?.data?.detail) {
        message.error(error.response.data.detail)
      } else {
        message.error('投稿失败，请稍后再试')
      }
    } finally {
      submittingTasks.value[record.task_id] = false
    }
  }

  const handleFavorite = async (record: any) => {
    if (record.is_favorited) return
    
    const hide = message.loading('正在收藏...', 0)
    try {
      await api.post(`/users/history/${record.task_id}/favorite`)
      hide()
      message.success('已收藏至修仙笔记')
      record.is_favorited = true
    } catch (error: any) {
      console.error(error)
      hide()
      message.error(error.response?.data?.detail || '收藏失败，请稍后再试')
    }
  }

  const handleDelete = async (record: any, event?: Event) => {
    if (event) event.stopPropagation()
    
    Modal.confirm({
      title: '确认删除',
      content: '确认删除该记录吗？（若已发布至广场也将同步下架）',
      okText: '确认',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await api.delete(`/users/history/${record.id}`)
          message.success('删除成功')
          if (options?.onDeleteSuccess) {
            options.onDeleteSuccess(record)
          }
        } catch (error: any) {
          console.error(error)
          message.error(error.response?.data?.detail || '删除失败，请稍后再试')
        }
      }
    })
  }

  const handleDownload = async (record: any) => {
    if (!record.output_file) return
    const url = resolveTaskDownloadUrl(record, getFileUrl)
    const ext = record.output_file.split('.').pop()?.toLowerCase() || (isVideoFile(record.output_file) ? 'mp4' : 'png')
    const filename = `${record.type}_${dayjs(record.created_at).format('YYYYMMDD_HHmmss')}.${ext}`
    
    const hide = message.loading('正在准备保存...', 0)
    try {
      const response = await fetch(url)
      if (!response.ok) throw new Error('Network response was not ok')
      const blob = await response.blob()
      
      let mimeType = blob.type
      if (!mimeType || mimeType === 'application/octet-stream') {
        if (ext === 'mp4') mimeType = 'video/mp4'
        else if (ext === 'png') mimeType = 'image/png'
        else if (ext === 'jpg' || ext === 'jpeg') mimeType = 'image/jpeg'
        else if (ext === 'gif') mimeType = 'image/gif'
      }
      
      const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent)
      
      if (isMobile && navigator.canShare) {
        const file = new File([blob], filename, { type: mimeType })
        if (navigator.canShare({ files: [file] })) {
          hide()
          try {
            await navigator.share({
              files: [file],
              title: '保存作品'
            })
            return
          } catch (e: any) {
            if (e.name !== 'AbortError') {
              console.warn('Share API failed, fallback to download:', e)
            } else {
              return
            }
          }
        }
      }

      const objectUrl = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(objectUrl)
      hide()
      message.success(isMobile ? '已触发下载，若未保存成功请点击预览图长按保存' : '下载成功')
    } catch (error) {
      console.warn('Fetch download failed, falling back to new tab', error)
      hide()
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.target = '_blank'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      message.info('已在新标签页打开，请长按保存')
    }
  }

  const handleSendToBot = async (record: any) => {
    if (!record.output_file) {
      message.warning('该记录无文件可发送')
      return
    }
    
    const hide = message.loading('正在发送至私聊...', 0)
    try {
      await api.post(`/users/history/${record.task_id}/send-to-bot`)
      hide()
      message.success('已发送至您的私聊，请在 Telegram 中查收')
    } catch (error: any) {
      console.error(error)
      hide()
      message.error(error.response?.data?.detail || '发送失败，请确保机器人未被屏蔽')
    }
  }

  return {
    submittingTasks,
    submitToGallery,
    handleFavorite,
    handleDelete,
    handleDownload,
    handleSendToBot
  }
}
