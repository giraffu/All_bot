import { ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  requestPresignedUpload,
  uploadFileToPresignedUrl
} from '@/utils/presignedUpload'

export type UploadFileOptions = {
  maxSizeBytes?: number
  maxSizeLabel?: string
}

const DEFAULT_MAX_SIZE_BYTES = 20 * 1024 * 1024
const DEFAULT_MAX_SIZE_LABEL = '20MB'

export function useUpload() {
  const uploading = ref(false)
  const progress = ref(0)

  const uploadFile = async (file: File, options: UploadFileOptions = {}): Promise<string | null> => {
    const maxSizeBytes = options.maxSizeBytes ?? DEFAULT_MAX_SIZE_BYTES
    const maxSizeLabel = options.maxSizeLabel ?? DEFAULT_MAX_SIZE_LABEL
    if (file.size > maxSizeBytes) {
      message.error(`文件大小不能超过 ${maxSizeLabel}，请压缩后再试`)
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
