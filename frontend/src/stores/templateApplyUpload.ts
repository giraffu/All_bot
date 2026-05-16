import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface TemplateApplyUploadHandle {
  uploadId: string
  sessionId: string
  slot: string
  xhr: XMLHttpRequest | null
  presignController: AbortController | null
  status: 'presigning' | 'pending' | 'uploading' | 'done' | 'aborted' | 'failed'
}

export const useTemplateApplyUploadStore = defineStore('templateApplyUpload', () => {
  const handles = ref<TemplateApplyUploadHandle[]>([])
  const isActiveStatus = (status: TemplateApplyUploadHandle['status']) =>
    status === 'presigning' || status === 'pending' || status === 'uploading'

  const abortHandle = (handle: TemplateApplyUploadHandle) => {
    handle.status = 'aborted'
    handle.presignController?.abort()
    handle.xhr?.abort()
  }

  const registerHandle = (handle: TemplateApplyUploadHandle) => {
    const replacedHandles = handles.value.filter(item =>
      item.sessionId === handle.sessionId
      && item.slot === handle.slot
      && item.uploadId !== handle.uploadId
      && isActiveStatus(item.status)
    )

    replacedHandles.forEach(item => {
      abortHandle(item)
    })

    handles.value = handles.value.filter(item =>
      !(item.sessionId === handle.sessionId && item.slot === handle.slot && item.uploadId !== handle.uploadId)
    )
    handles.value.push(handle)
  }

  const updateHandleTransport = (
    uploadId: string,
    transport: Partial<Pick<TemplateApplyUploadHandle, 'xhr' | 'presignController'>>
  ) => {
    const target = handles.value.find(item => item.uploadId === uploadId)
    if (!target) {
      return
    }

    if ('xhr' in transport) {
      target.xhr = transport.xhr ?? null
    }

    if ('presignController' in transport) {
      target.presignController = transport.presignController ?? null
    }
  }

  const updateStatus = (uploadId: string, status: TemplateApplyUploadHandle['status']) => {
    const target = handles.value.find(item => item.uploadId === uploadId)
    if (target) {
      target.status = status
    }
  }

  const removeHandle = (uploadId: string) => {
    handles.value = handles.value.filter(item => item.uploadId !== uploadId)
  }

  const abortUpload = (uploadId: string) => {
    const target = handles.value.find(item => item.uploadId === uploadId)
    if (!target) {
      return
    }

    abortHandle(target)
    removeHandle(uploadId)
  }

  const abortBySession = (sessionId: string) => {
    const sessionHandles = handles.value.filter(item => item.sessionId === sessionId)
    sessionHandles.forEach(handle => {
      abortHandle(handle)
    })
    handles.value = handles.value.filter(item => item.sessionId !== sessionId)
  }

  const isUploadStillActive = (uploadId: string, sessionId: string, slot: string) =>
    handles.value.some(item =>
      item.uploadId === uploadId
      && item.sessionId === sessionId
      && item.slot === slot
      && isActiveStatus(item.status)
    )

  const hasPendingUploads = (sessionId: string) =>
    handles.value.some(item =>
      item.sessionId === sessionId
      && isActiveStatus(item.status)
    )

  return {
    handles,
    registerHandle,
    updateHandleTransport,
    updateStatus,
    removeHandle,
    abortUpload,
    abortBySession,
    isUploadStillActive,
    hasPendingUploads
  }
})
