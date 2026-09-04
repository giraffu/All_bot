import { message } from 'ant-design-vue'
import { computed, ref } from 'vue'

import type {
  H3ReferenceVideoClipDuration,
  TranslateFn,
  UploadedReferenceVideo,
  UploadFileFn,
} from './types'

export const H3_REFERENCE_VIDEO_MAX_DURATION_SECONDS = 40
export const H3_REFERENCE_VIDEO_CLIP_DURATIONS: readonly H3ReferenceVideoClipDuration[] = [3, 5, 10, 15]
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
  const referenceVideoClipDuration = ref<H3ReferenceVideoClipDuration>(5)
  const referenceVideoClipDurationOptions = computed(() => (
    H3_REFERENCE_VIDEO_CLIP_DURATIONS.filter(
      duration => duration <= (referenceVideo.value?.durationSeconds ?? 0) + 1e-6,
    )
  ))

  const clearReferenceVideo = () => {
    if (referenceVideo.value?.preview.startsWith('blob:')) {
      URL.revokeObjectURL(referenceVideo.value.preview)
    }
    referenceVideo.value = null
    referenceVideoClipDuration.value = 5
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
      if (durationSeconds + 1e-6 < H3_REFERENCE_VIDEO_CLIP_DURATIONS[0]) {
        message.warning(t('lab.workbench.validation.minimax_h3_reference_video_too_short'))
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
      referenceVideoClipDuration.value = durationSeconds >= 5 ? 5 : 3
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
    referenceVideoClipDuration,
    referenceVideoClipDurationOptions,
    beforeUploadReferenceVideo,
    clearReferenceVideo,
  }
}
