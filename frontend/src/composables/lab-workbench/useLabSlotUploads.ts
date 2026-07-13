import { computed, ref, type Ref } from 'vue'

import type { LabModeConfig, LabUploadPreviewKind, LabUploadSlotId } from '@/features/generation/labModeConfig'
import { isScail2ModeId } from './modeHelpers'
import { revokeReferencePreview } from './useLabReferenceUploads'
import type {
  LabAssetUploadSlot,
  TranslateFn,
  UploadedSlotAsset,
  UploadFileFn,
} from './types'

export const SCAIL2_VIDEO_UPLOAD_MAX_SIZE_BYTES = 40 * 1024 * 1024
export const SCAIL2_VIDEO_UPLOAD_MAX_SIZE_LABEL = '40MB'

type UseLabSlotUploadsOptions = {
  currentMode: Ref<LabModeConfig>
  uploadProgress: Ref<number>
  uploadFile: UploadFileFn
  t: TranslateFn
}

export function useLabSlotUploads({
  currentMode,
  uploadProgress,
  uploadFile,
  t,
}: UseLabSlotUploadsOptions) {
  const uploadedSlotAssets = ref<Partial<Record<LabUploadSlotId, UploadedSlotAsset>>>({})
  const scail2MotionVideoDurationSeconds = ref<number | null>(null)
  const pendingSlotUploadCount = ref(0)

  const assetUploadSlots = computed<LabAssetUploadSlot[]>(() => (
    currentMode.value.uploadSlots?.map((slot) => {
      const item = uploadedSlotAssets.value[slot.id] ?? null
      return {
        id: slot.id,
        label: t(slot.labelKey),
        hint: t(slot.hintKey),
        buttonLabel: t(slot.buttonKey),
        accept: slot.accept,
        previewKind: slot.previewKind,
        required: slot.required,
        item: item
          ? {
              ...item,
              progress: item.uploading ? uploadProgress.value : undefined,
            }
          : null,
      }
    }) ?? []
  ))

  const clearSlotAssets = () => {
    Object.values(uploadedSlotAssets.value).forEach(item => revokeReferencePreview(item?.preview))
    uploadedSlotAssets.value = {}
    scail2MotionVideoDurationSeconds.value = null
  }

  const handleRemoveUploadSlot = (slotId: LabUploadSlotId) => {
    const target = uploadedSlotAssets.value[slotId]
    revokeReferencePreview(target?.preview)
    delete uploadedSlotAssets.value[slotId]
    if (slotId === 'motion_video') {
      scail2MotionVideoDurationSeconds.value = null
    }
  }

  const handleAssetVideoMetadata = (slotId: LabUploadSlotId, durationSeconds: number | null) => {
    if (!isScail2ModeId(currentMode.value.id) || slotId !== 'motion_video') {
      return
    }
    scail2MotionVideoDurationSeconds.value = durationSeconds
  }

  const shouldLimitStructuredVideoUpload = (slotId: LabUploadSlotId) => (
    (isScail2ModeId(currentMode.value.id) && slotId === 'motion_video')
  )

  const beforeUploadSlot = async (slotId: LabUploadSlotId, file: File) => {
    const slot = currentMode.value.uploadSlots?.find(item => item.id === slotId)
    if (!slot) {
      return false
    }

    pendingSlotUploadCount.value += 1
    const preview = URL.createObjectURL(file)
    const pendingKey = `pending-${slotId}-${Date.now()}-${file.name}`
    let objectKey: string | null | undefined = null
    handleRemoveUploadSlot(slotId)
    uploadedSlotAssets.value[slotId] = {
      key: pendingKey,
      preview,
      name: file.name,
      previewKind: slot.previewKind,
      uploading: true,
    }

    try {
      objectKey = await uploadFile(
        file,
        slot.previewKind === 'video' && shouldLimitStructuredVideoUpload(slotId)
          ? {
              maxSizeBytes: SCAIL2_VIDEO_UPLOAD_MAX_SIZE_BYTES,
              maxSizeLabel: SCAIL2_VIDEO_UPLOAD_MAX_SIZE_LABEL,
            }
          : undefined,
      )
      if (!objectKey) {
        return false
      }

      uploadedSlotAssets.value[slotId] = {
        key: objectKey,
        preview,
        name: file.name,
        previewKind: slot.previewKind,
      }
      return false
    } finally {
      if (!objectKey && uploadedSlotAssets.value[slotId]?.key === pendingKey) {
        delete uploadedSlotAssets.value[slotId]
        revokeReferencePreview(preview)
      }
      pendingSlotUploadCount.value -= 1
    }
  }

  const applySlotTemplateTarget = (
    slotId: LabUploadSlotId,
    target: { objectKey: string; previewUrl?: string | null; name: string; previewKind: LabUploadPreviewKind },
  ) => {
    handleRemoveUploadSlot(slotId)
    uploadedSlotAssets.value[slotId] = {
      key: target.objectKey,
      preview: target.previewUrl ?? '',
      name: target.name,
      previewKind: target.previewKind,
    }
  }

  return {
    uploadedSlotAssets,
    scail2MotionVideoDurationSeconds,
    pendingSlotUploadCount,
    assetUploadSlots,
    clearSlotAssets,
    handleRemoveUploadSlot,
    handleAssetVideoMetadata,
    beforeUploadSlot,
    applySlotTemplateTarget,
  }
}
