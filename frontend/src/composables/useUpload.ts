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
          // Since the backend MinIO SDK version doesn't support signing the Content-Type header easily,
          // the presigned URL is generated WITHOUT a Content-Type constraint.
          // Therefore, the browser MUST NOT send any Content-Type header, otherwise MinIO 
          // returns a 403 SignatureDoesNotMatch.
          
          // Force clear Content-Type 
          xhr.setRequestHeader('Content-Type', '')
          
          xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
              progress.value = Math.round((e.loaded * 100) / e.total)
            }
          }
          
          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              resolve(object_key)
            } else {
              console.error(`Upload failed with status ${xhr.status}:`, xhr.responseText)
              reject(new Error(`Upload failed with status ${xhr.status}`))
            }
          }
          
          xhr.onerror = () => reject(new Error('Network error during upload'))
          
          // IMPORTANT: Convert the File to a Blob with an empty type string.
          // This strips the MIME type (like 'image/jpeg') so the browser's XMLHttpRequest 
          // won't automatically inject the Content-Type header when sending.
          const blobToUpload = new Blob([file], { type: '' })
          xhr.send(blobToUpload)
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
