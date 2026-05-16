import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useTemplateApplyUploadStore, type TemplateApplyUploadHandle } from '@/stores/templateApplyUpload'

const createHandle = (
  uploadId: string,
  sessionId = 'session-a',
  slot = 'image_0'
): TemplateApplyUploadHandle => {
  const abort = vi.fn()
  return {
    uploadId,
    sessionId,
    slot,
    status: 'uploading',
    xhr: { abort } as unknown as XMLHttpRequest,
    presignController: null
  }
}

describe('templateApplyUpload store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('replaces active upload in the same session slot and aborts the old xhr', () => {
    const store = useTemplateApplyUploadStore()
    const first = createHandle('upload-1')
    const second = createHandle('upload-2')

    store.registerHandle(first)
    store.registerHandle(second)

    expect((first.xhr!.abort as unknown as ReturnType<typeof vi.fn>)).toHaveBeenCalledTimes(1)
    expect(store.handles).toHaveLength(1)
    expect(store.handles[0]?.uploadId).toBe('upload-2')
    expect(store.isUploadStillActive('upload-1', 'session-a', 'image_0')).toBe(false)
    expect(store.isUploadStillActive('upload-2', 'session-a', 'image_0')).toBe(true)
  })

  it('aborts and clears all uploads for one session only', () => {
    const store = useTemplateApplyUploadStore()
    const handleA = createHandle('upload-a', 'session-a', 'image_0')
    const handleB = createHandle('upload-b', 'session-a', 'image_1')
    const handleC = createHandle('upload-c', 'session-b', 'image_0')

    store.registerHandle(handleA)
    store.registerHandle(handleB)
    store.registerHandle(handleC)

    store.abortBySession('session-a')

    expect((handleA.xhr!.abort as unknown as ReturnType<typeof vi.fn>)).toHaveBeenCalledTimes(1)
    expect((handleB.xhr!.abort as unknown as ReturnType<typeof vi.fn>)).toHaveBeenCalledTimes(1)
    expect((handleC.xhr!.abort as unknown as ReturnType<typeof vi.fn>)).not.toHaveBeenCalled()
    expect(store.handles.map(item => item.uploadId)).toEqual(['upload-c'])
    expect(store.hasPendingUploads('session-a')).toBe(false)
    expect(store.hasPendingUploads('session-b')).toBe(true)
  })

  it('treats presigning uploads as active and aborts the presign controller', () => {
    const store = useTemplateApplyUploadStore()
    const abort = vi.fn()

    store.registerHandle({
      uploadId: 'upload-presign',
      sessionId: 'session-a',
      slot: 'image_0',
      status: 'presigning',
      xhr: null,
      presignController: { abort } as unknown as AbortController
    })

    expect(store.hasPendingUploads('session-a')).toBe(true)
    expect(store.isUploadStillActive('upload-presign', 'session-a', 'image_0')).toBe(true)

    store.abortBySession('session-a')

    expect(abort).toHaveBeenCalledTimes(1)
    expect(store.hasPendingUploads('session-a')).toBe(false)
  })
})
