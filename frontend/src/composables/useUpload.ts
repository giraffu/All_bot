import { ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  requestPresignedUpload,
  uploadFileToPresignedUrl
} from '@/utils/presignedUpload'

export function useUpload() {
  const uploading = ref(false)
  const progress = ref(0)

  const uploadFile = async (file: File): Promise<string | null> => {
    // 限制上传文件大小为 20MB
    const MAX_SIZE = 20 * 1024 * 1024;
    if (file.size > MAX_SIZE) {
      message.error('文件大小不能超过 20MB，请压缩后再试');
      return null;
    }

    uploading.value = true
    progress.value = 0
    
    try {
      const payload = await requestPresignedUpload(file)
      const objectKey = await uploadFileToPresignedUrl(file, payload, {
        onProgress: (event) => {
          if (event.lengthComputable) {
            progress.value = Math.round((event.loaded * 100) / event.total)
          }
        }
      })

      message.success('文件上传成功')
      return objectKey
      
    } catch (error: any) {
      console.error('Upload error:', error)
      const errorMessage = error?.message === 'Network error during upload'
        ? 'Network error during upload (可能是服务器繁忙或跨域拦截，请稍后再试)'
        : (error?.message || '文件上传失败')
      message.error(errorMessage)
      return null
    } finally {
      uploading.value = false
      progress.value = 0
    }
  }

  return {
    uploading,
    progress,
    uploadFile
  }
}
