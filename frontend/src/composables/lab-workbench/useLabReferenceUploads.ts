import { computed, ref, type Ref } from 'vue'
import { message } from 'ant-design-vue'

import type { LabModeConfig } from '@/features/generation/labModeConfig'
import type {
  PendingReferenceUpload,
  TranslateFn,
  UploadedReference,
  UploadFileFn,
} from './types'

export const revokeReferencePreview = (previewUrl: string | null | undefined) => {
  if (previewUrl?.startsWith('blob:')) {
    URL.revokeObjectURL(previewUrl)
  }
}

type UseLabReferenceUploadsOptions = {
  currentMode: Ref<LabModeConfig>
  uploadProgress: Ref<number>
  uploadFile: UploadFileFn
  t: TranslateFn
}

export function useLabReferenceUploads({
  currentMode,
  uploadProgress,
  uploadFile,
  t,
}: UseLabReferenceUploadsOptions) {
  const uploadedReferences = ref<UploadedReference[]>([])
  const pendingReferenceUploads = ref<PendingReferenceUpload[]>([])
  const pendingReferenceUploadCount = ref(0)

  const displayedReferences = computed(() => [
    ...uploadedReferences.value,
    ...pendingReferenceUploads.value.map(item => ({
      ...item,
      progress: uploadProgress.value,
    })),
  ])

  const canUploadReference = computed(() => (
    currentMode.value.supportsUpload
    && uploadedReferences.value.length + pendingReferenceUploads.value.length < currentMode.value.maxImages
  ))

  const clearReferences = () => {
    uploadedReferences.value.forEach(item => revokeReferencePreview(item.preview))
    pendingReferenceUploads.value.forEach(item => revokeReferencePreview(item.preview))
    uploadedReferences.value = []
    pendingReferenceUploads.value = []
  }

  const handleRemoveReference = (index: number) => {
    const target = uploadedReferences.value[index]
    if (target?.locked) {
      message.info(target.lockedLabel || t('lab.workbench.wan22_locked_start_frame'))
      return
    }
    revokeReferencePreview(target?.preview)
    uploadedReferences.value.splice(index, 1)
  }

  const beforeUpload = async (file: File) => {
    if (uploadedReferences.value.length + pendingReferenceUploads.value.length >= currentMode.value.maxImages) {
      message.warning(
        t('template_apply.image_prompt.max_images_warning', {
          count: currentMode.value.maxImages,
        }),
      )
      return false
    }

    pendingReferenceUploadCount.value += 1
    const pendingKey = `pending-${Date.now()}-${file.name}`
    const preview = URL.createObjectURL(file)
    let objectKey: string | null | undefined = null
    let imageDimensions: { width: number, height: number } | undefined
    if (file.type.startsWith('image/') && typeof createImageBitmap === 'function') {
      try {
        const bitmap = await createImageBitmap(file)
        imageDimensions = { width: bitmap.width, height: bitmap.height }
        bitmap.close()
      }
      catch {
        // Dimension inference is best-effort; backend validation stays authoritative.
      }
    }
    pendingReferenceUploads.value.push({
      key: pendingKey,
      preview,
      name: file.name,
      uploading: true,
    })

    try {
      objectKey = await uploadFile(file)
      if (!objectKey) {
        return false
      }

      uploadedReferences.value.push({
        key: objectKey,
        preview,
        name: file.name,
        ...imageDimensions,
      })
      return false
    } finally {
      pendingReferenceUploads.value = pendingReferenceUploads.value.filter(item => item.key !== pendingKey)
      if (!objectKey) {
        revokeReferencePreview(preview)
      }
      pendingReferenceUploadCount.value -= 1
    }
  }

  return {
    uploadedReferences,
    pendingReferenceUploads,
    pendingReferenceUploadCount,
    displayedReferences,
    canUploadReference,
    beforeUpload,
    clearReferences,
    handleRemoveReference,
  }
}
