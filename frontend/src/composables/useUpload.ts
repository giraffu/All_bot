import { ref } from 'vue'
import api from '@/api'
import { message } from 'ant-design-vue'

export function useUpload() {
  const uploading = ref(false)
  const progress = ref(0)

  const uploadFile = async (file: File): Promise<string | null> => {
    uploading.value = true
    progress.value = 0
    
    try {
      // 1. Get presigned URL
      const { data } = await api.get('/storage/presigned-url', {
        params: {
          filename: file.name,
          content_type: file.type || 'application/octet-stream'
        }
      })

      const { upload_url, object_key } = data

      // 2. Direct upload to MinIO via PUT
      // Use native XMLHttpRequest or fresh Axios instance without interceptors
      // because we don't want to send our JWT to MinIO
      await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('PUT', upload_url, true)
        
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            progress.value = Math.round((e.loaded / e.total) * 100)
          }
        }
        
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(xhr.response)
          } else {
            reject(new Error(`Upload failed with status ${xhr.status}`))
          }
        }
        
        xhr.onerror = () => reject(new Error('Network error during upload'))
        
        xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream')
        xhr.send(file)
      })

      message.success('文件上传成功')
      return object_key
      
    } catch (error: any) {
      console.error('Upload error:', error)
      message.error(error.message || '文件上传失败')
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
