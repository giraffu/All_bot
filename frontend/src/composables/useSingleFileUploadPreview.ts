import { onBeforeUnmount, ref, watch } from 'vue'
import type { UploadFileLike } from '@/types/upload'

interface UseSingleFileUploadPreviewOptions {
  uploadFile: (file: File) => Promise<string | null | undefined>
}

export function useSingleFileUploadPreview(
  options: UseSingleFileUploadPreviewOptions
) {
  const fileList = ref<Array<UploadFileLike | File>>([])
  const objectKey = ref<string | null>(null)
  const filePreview = ref<string | null>(null)

  const revokePreview = () => {
    if (filePreview.value) {
      URL.revokeObjectURL(filePreview.value)
      filePreview.value = null
    }
  }

  const resolveOriginFile = (file: UploadFileLike | File): File | null => {
    if (file instanceof File) {
      return file
    }
    return file.originFileObj ?? null
  }

  watch(fileList, (newVal) => {
    const file = newVal.length > 0 ? resolveOriginFile(newVal[0]) : null
    if (file) {
      revokePreview()
      filePreview.value = URL.createObjectURL(file)
    } else {
      revokePreview()
    }
  })

  const beforeUpload = async (file: File) => {
    fileList.value = [file]
    const key = await options.uploadFile(file)
    if (key) {
      objectKey.value = key
    }
    return false
  }

  const handleRemove = () => {
    fileList.value = []
    objectKey.value = null
  }

  const setRemoteFile = (key: string | null, previewUrl: string | null) => {
    fileList.value = []
    objectKey.value = key
    revokePreview()
    filePreview.value = previewUrl
  }

  onBeforeUnmount(() => {
    revokePreview()
  })

  return {
    fileList,
    objectKey,
    filePreview,
    beforeUpload,
    handleRemove,
    setRemoteFile,
  }
}
