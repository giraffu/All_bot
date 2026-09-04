import { message } from 'ant-design-vue'
import { ref } from 'vue'

import type { TranslateFn, UploadedReferenceVideo, UploadFileFn } from './types'

export const H3_REFERENCE_VIDEO_MAX_DURATION_SECONDS = 40
export const H3_REFERENCE_VIDEO_CLIP_SECONDS = 5
export const H3_REFERENCE_VIDEO_MAX_BYTES = 40 * 1024 * 1024

export const readVideoDurationSeconds = (file: File): Promise<number> => (
  new Promise((resolve, reject) => {
    const preview = URL.createObjectURL(file)
    const video = document.createElement('video')
    video.preload = 'metadata'
    video.onloadedmetadata = () => {
      const duration = video.duration
      URL.revokeObjectURL(preview)
      Number.isFinite(duration) && duration > 0
        ? resolve(duration)
        : reject(new Error('video_duration_unavailable'))
    }
    video.onerror = () => {
      URL.revokeObjectURL(preview)
      reject(new Error('video_duration_unavailable'))
    }
    video.src = preview
  })
)

type UseH3ReferenceVideoOptions = {
  uploadFile: UploadFileFn
  t: TranslateFn
  readDuration?: (file: File) => Promise<number>
}

export function useH3ReferenceVideo({
  uploadFile,
  t,
  readDuration = readVideoDurationSeconds,
}: UseH3ReferenceVideoOptions) {
  const referenceVideo = ref<UploadedReferenceVideo | null>(null)
  const referenceVideoUploading = ref(false)

  const clearReferenceVideo = () => {
    if (referenceVideo.value?.preview.startsWith('blob:')) {
      URL.revokeObjectURL(referenceVideo.value.preview)
    }
    referenceVideo.value = null
  }

  const beforeUploadReferenceVideo = async (file: File) => {
    referenceVideoUploading.value = true
    let preview: string | null = null
    let objectKey: string | null | undefined
    try {
      const durationSeconds = await readDuration(file)
      if (durationSeconds > H3_REFERENCE_VIDEO_MAX_DURATION_SECONDS) {
        message.warning(t('lab.workbench.validation.minimax_h3_reference_video_too_long'))
        return false
      }
      preview = URL.createObjectURL(file)
      objectKey = await uploadFile(file, {
        maxSizeBytes: H3_REFERENCE_VIDEO_MAX_BYTES,
        maxSizeLabel: t('lab.workbench.minimax_h3_reference_video_size'),
      })
      if (!objectKey) return false
      clearReferenceVideo()
      referenceVideo.value = {
        key: objectKey,
        preview,
        name: file.name,
        durationSeconds,
      }
      return false
    }
    catch {
      message.warning(t('lab.workbench.validation.minimax_h3_reference_video_unreadable'))
      return false
    }
    finally {
      if (!objectKey && preview) URL.revokeObjectURL(preview)
      referenceVideoUploading.value = false
    }
  }

  return {
    referenceVideo,
    referenceVideoUploading,
    beforeUploadReferenceVideo,
    clearReferenceVideo,
  }
}
