import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'
import { message } from 'ant-design-vue'
import i18n from '@/i18n'
import { useTemplateApplyStore } from '@/stores/templateApply'
import { useTemplateApplyUploadStore } from '@/stores/templateApplyUpload'
import {
  requestPresignedUpload,
  uploadFileToPresignedUrl
} from '@/utils/presignedUpload'

const MAX_UPLOAD_SIZE = 20 * 1024 * 1024
const t = (key: string, params?: Record<string, unknown>) =>
  params ? i18n.global.t(key, params) : i18n.global.t(key)

const createUploadId = () =>
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `upload_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

export function useTemplateApplyUpload(sessionIdSource: MaybeRefOrGetter<string>) {
  const uploadStore = useTemplateApplyUploadStore()
  const templateApplyStore = useTemplateApplyStore()
  const uploadingSlots = ref<Record<string, boolean>>({})
  const progressBySlot = ref<Record<string, number>>({})
  const activeUploadIdBySlot = ref<Record<string, string | null>>({})

  const hasPendingUploads = computed(() => {
    const sessionId = toValue(sessionIdSource)
    return sessionId ? uploadStore.hasPendingUploads(sessionId) : false
  })

  const isCurrentSlotUpload = (slot: string, uploadId: string) =>
    activeUploadIdBySlot.value[slot] === uploadId

  const resetSlotState = (slot: string, uploadId: string) => {
    if (!isCurrentSlotUpload(slot, uploadId)) {
      return
    }

    activeUploadIdBySlot.value = {
      ...activeUploadIdBySlot.value,
      [slot]: null
    }
    uploadingSlots.value = {
      ...uploadingSlots.value,
      [slot]: false
    }
    progressBySlot.value = {
      ...progressBySlot.value,
      [slot]: 0
    }
  }

  const uploadFile = async (
    file: File,
    options: { slot: string }
  ): Promise<{ uploadId: string; objectKey: string | null }> => {
    if (file.size > MAX_UPLOAD_SIZE) {
      message.error(t('template_apply.common.file_too_large'))
      return {
        uploadId: '',
        objectKey: null
      }
    }

    const sessionId = toValue(sessionIdSource)
    const uploadId = createUploadId()
    const slot = options.slot
    const isSessionAlive = () =>
      !!sessionId && templateApplyStore.isSessionActive(sessionId)

    if (!isSessionAlive()) {
      return {
        uploadId,
        objectKey: null
      }
    }

    uploadingSlots.value = {
      ...uploadingSlots.value,
      [slot]: true
    }
    progressBySlot.value = {
      ...progressBySlot.value,
      [slot]: 0
    }
    activeUploadIdBySlot.value = {
      ...activeUploadIdBySlot.value,
      [slot]: uploadId
    }

    const presignController = new AbortController()
    uploadStore.registerHandle({
      uploadId,
      sessionId,
      slot,
      xhr: null,
      presignController,
      status: 'presigning'
    })

    try {
      if (!uploadStore.isUploadStillActive(uploadId, sessionId, slot) || !isSessionAlive()) {
        uploadStore.updateStatus(uploadId, 'aborted')
        return {
          uploadId,
          objectKey: null
        }
      }

      const payload = await requestPresignedUpload(file, {
        signal: presignController.signal
      })

      if (!uploadStore.isUploadStillActive(uploadId, sessionId, slot) || !isSessionAlive()) {
        uploadStore.updateStatus(uploadId, 'aborted')
        return {
          uploadId,
          objectKey: null
        }
      }

      const xhr = new XMLHttpRequest()

      uploadStore.updateHandleTransport(uploadId, {
        xhr,
        presignController: null
      })
      uploadStore.updateStatus(uploadId, 'pending')

      const objectKey = await uploadFileToPresignedUrl(file, payload, {
        xhr,
        beforeSend: () => {
          if (!uploadStore.isUploadStillActive(uploadId, sessionId, slot) || !isSessionAlive()) {
            return false
          }
          uploadStore.updateStatus(uploadId, 'uploading')
          return true
        },
        onProgress: (event) => {
          if (!event.lengthComputable || !isCurrentSlotUpload(slot, uploadId)) {
            return
          }

          progressBySlot.value = {
            ...progressBySlot.value,
            [slot]: Math.round((event.loaded * 100) / event.total)
          }
        },
        onAbort: () => {
          uploadStore.updateStatus(uploadId, 'aborted')
        }
      })

      if (
        objectKey &&
        (!uploadStore.isUploadStillActive(uploadId, sessionId, slot) || !isSessionAlive())
      ) {
        return {
          uploadId,
          objectKey: null
        }
      }

      if (objectKey) {
        uploadStore.updateStatus(uploadId, 'done')
      }

      if (objectKey) {
        message.success(t('template_apply.common.upload_success'))
      }

      return {
        uploadId,
        objectKey
      }
    } catch (error: any) {
      if (error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED') {
        uploadStore.updateStatus(uploadId, 'aborted')
        return {
          uploadId,
          objectKey: null
        }
      }

      console.error('Template apply upload error:', error)
      uploadStore.updateStatus(uploadId, 'failed')
      message.error(error.message || t('template_apply.common.upload_failed'))
      return {
        uploadId,
        objectKey: null
      }
    } finally {
      uploadStore.removeHandle(uploadId)
      resetSlotState(slot, uploadId)
    }
  }

  return {
    uploadingSlots,
    progressBySlot,
    hasPendingUploads,
    uploadFile
  }
}
