import { ref } from 'vue'

import type { TranslateFn, UploadedReferenceAudio, UploadFileFn } from './types'

const MAX_REFERENCE_AUDIO_BYTES = 20 * 1024 * 1024

type UseH3ReferenceAudioOptions = {
  uploadFile: UploadFileFn
  t: TranslateFn
}

export function useH3ReferenceAudio({ uploadFile, t }: UseH3ReferenceAudioOptions) {
  const referenceAudio = ref<UploadedReferenceAudio | null>(null)
  const referenceAudioUploading = ref(false)

  const clearReferenceAudio = () => {
    if (referenceAudio.value?.preview.startsWith('blob:')) {
      URL.revokeObjectURL(referenceAudio.value.preview)
    }
    referenceAudio.value = null
  }

  const beforeUploadReferenceAudio = async (file: File) => {
    referenceAudioUploading.value = true
    const preview = URL.createObjectURL(file)
    let objectKey: string | null | undefined
    try {
      objectKey = await uploadFile(file, {
        maxSizeBytes: MAX_REFERENCE_AUDIO_BYTES,
        maxSizeLabel: t('lab.workbench.minimax_h3_reference_audio_size'),
      })
      if (!objectKey) return false
      clearReferenceAudio()
      referenceAudio.value = { key: objectKey, preview, name: file.name }
      return false
    }
    finally {
      if (!objectKey) URL.revokeObjectURL(preview)
      referenceAudioUploading.value = false
    }
  }

  return {
    referenceAudio,
    referenceAudioUploading,
    beforeUploadReferenceAudio,
    clearReferenceAudio,
  }
}
