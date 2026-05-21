import { onBeforeUnmount, ref, watch } from 'vue'

interface UploadListItemLike {
  originFileObj?: File
}

interface UseSingleFileUploadPreviewOptions {
  uploadFile: (file: any) => Promise<string | null | undefined>
}

export function useSingleFileUploadPreview(
  options: UseSingleFileUploadPreviewOptions
) {
  const fileList = ref<any[]>([])
  const objectKey = ref<string | null>(null)
  const filePreview = ref<string | null>(null)

  const revokePreview = () => {
    if (filePreview.value) {
      URL.revokeObjectURL(filePreview.value)
      filePreview.value = null
    }
  }

  watch(fileList, (newVal: UploadListItemLike[]) => {
    if (newVal.length > 0 && newVal[0].originFileObj) {
      revokePreview()
      filePreview.value = URL.createObjectURL(newVal[0].originFileObj)
    } else if (newVal.length > 0 && newVal[0] instanceof File) {
      revokePreview()
      filePreview.value = URL.createObjectURL(newVal[0])
    } else {
      revokePreview()
    }
  })

  const beforeUpload = async (file: any) => {
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

  onBeforeUnmount(() => {
    revokePreview()
  })

  return {
    fileList,
    objectKey,
    filePreview,
    beforeUpload,
    handleRemove,
  }
}
