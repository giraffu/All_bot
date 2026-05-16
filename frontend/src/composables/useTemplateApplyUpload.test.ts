// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useTemplateApplyStore } from '@/stores/templateApply'
import { useTemplateApplyUploadStore } from '@/stores/templateApplyUpload'
import { useTemplateApplyUpload } from '@/composables/useTemplateApplyUpload'

const {
  apiGetMock,
  messageSuccessMock,
  messageErrorMock,
  messageWarningMock
} = vi.hoisted(() => ({
  apiGetMock: vi.fn(),
  messageSuccessMock: vi.fn(),
  messageErrorMock: vi.fn(),
  messageWarningMock: vi.fn()
}))

vi.mock('@/api', () => ({
  default: {
    get: apiGetMock
  }
}))

vi.mock('ant-design-vue', () => ({
  message: {
    success: messageSuccessMock,
    error: messageErrorMock,
    warning: messageWarningMock
  }
}))

const flushMicrotasks = async () => {
  await Promise.resolve()
  await Promise.resolve()
}

class MockXMLHttpRequest {
  static instances: MockXMLHttpRequest[] = []

  status = 200
  upload = {
    onprogress: null as ((event: ProgressEvent<EventTarget>) => void) | null
  }
  onload: (() => void) | null = null
  onabort: (() => void) | null = null
  onerror: (() => void) | null = null
  open = vi.fn()
  send = vi.fn()
  abort = vi.fn(() => {
    this.onabort?.()
  })

  constructor() {
    MockXMLHttpRequest.instances.push(this)
  }
}

describe('useTemplateApplyUpload', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    apiGetMock.mockReset()
    messageSuccessMock.mockReset()
    messageErrorMock.mockReset()
    messageWarningMock.mockReset()
    MockXMLHttpRequest.instances = []

    vi.stubGlobal('XMLHttpRequest', MockXMLHttpRequest as unknown as typeof XMLHttpRequest)
  })

  it('aborts the presign request when the workbench session closes before presign resolves', async () => {
    const templateApplyStore = useTemplateApplyStore()
    const uploadStore = useTemplateApplyUploadStore()

    const opened = await templateApplyStore.openFromRawContext({
      source: 'gallery',
      entryEntityId: 10,
      rawContext: {
        post_id: 10,
        source_post_id: 10,
        task_type: 'face_swap',
        input_file: 'history/demo/original.png'
      }
    })

    if (opened.status !== 'opened') {
      throw new Error('Expected template workbench session to open')
    }

    apiGetMock.mockImplementation((_url: string, config?: { signal?: AbortSignal }) =>
      new Promise((_resolve, reject) => {
        config?.signal?.addEventListener('abort', () => {
          const cancelError = Object.assign(new Error('canceled'), {
            name: 'CanceledError',
            code: 'ERR_CANCELED'
          })
          reject(cancelError)
        })
      })
    )

    const { uploadFile, hasPendingUploads } = useTemplateApplyUpload(computed(() => opened.sessionId))
    const uploadPromise = uploadFile(
      new File(['face'], 'face.png', { type: 'image/png' }),
      { slot: 'face_image' }
    )

    expect(hasPendingUploads.value).toBe(true)
    expect(uploadStore.hasPendingUploads(opened.sessionId)).toBe(true)

    await templateApplyStore.confirmCloseAndCleanup('user_close')

    const result = await uploadPromise

    expect(result).toEqual({
      uploadId: expect.any(String),
      objectKey: null
    })
    expect(uploadStore.hasPendingUploads(opened.sessionId)).toBe(false)
    expect(templateApplyStore.visible).toBe(false)
    expect(messageErrorMock).not.toHaveBeenCalled()
    expect(messageSuccessMock).not.toHaveBeenCalled()
  })

  it('keeps the latest slot upload state when an older upload in the same slot finishes later', async () => {
    const templateApplyStore = useTemplateApplyStore()

    const opened = await templateApplyStore.openFromRawContext({
      source: 'gallery',
      entryEntityId: 10,
      rawContext: {
        post_id: 10,
        source_post_id: 10,
        task_type: 'face_swap',
        input_file: 'history/demo/original.png'
      }
    })

    if (opened.status !== 'opened') {
      throw new Error('Expected template workbench session to open')
    }

    apiGetMock
      .mockResolvedValueOnce({
        data: {
          upload_url: 'https://example.com/upload-first',
          object_key: 'uploads/first.png'
        }
      })
      .mockResolvedValueOnce({
        data: {
          upload_url: 'https://example.com/upload-second',
          object_key: 'uploads/second.png'
        }
      })

    const { uploadFile, uploadingSlots, progressBySlot } = useTemplateApplyUpload(
      computed(() => opened.sessionId)
    )

    const firstPromise = uploadFile(
      new File(['first'], 'first.png', { type: 'image/png' }),
      { slot: 'face_image' }
    )

    await flushMicrotasks()

    const firstXhr = MockXMLHttpRequest.instances[0]
    if (!firstXhr?.upload.onprogress) {
      throw new Error('Expected the first upload xhr to be initialized')
    }

    firstXhr.upload.onprogress({
      lengthComputable: true,
      loaded: 25,
      total: 100
    } as ProgressEvent<EventTarget>)
    expect(progressBySlot.value.face_image).toBe(25)
    expect(uploadingSlots.value.face_image).toBe(true)

    const secondPromise = uploadFile(
      new File(['second'], 'second.png', { type: 'image/png' }),
      { slot: 'face_image' }
    )

    await flushMicrotasks()

    const secondXhr = MockXMLHttpRequest.instances[1]
    if (!secondXhr?.upload.onprogress) {
      throw new Error('Expected the second upload xhr to be initialized')
    }

    expect(firstXhr.abort).toHaveBeenCalledTimes(1)
    expect(uploadingSlots.value.face_image).toBe(true)
    expect(progressBySlot.value.face_image).toBe(0)

    secondXhr.upload.onprogress({
      lengthComputable: true,
      loaded: 60,
      total: 100
    } as ProgressEvent<EventTarget>)
    expect(progressBySlot.value.face_image).toBe(60)

    firstXhr.upload.onprogress({
      lengthComputable: true,
      loaded: 90,
      total: 100
    } as ProgressEvent<EventTarget>)
    expect(progressBySlot.value.face_image).toBe(60)

    const firstResult = await firstPromise
    expect(firstResult.objectKey).toBeNull()
    expect(uploadingSlots.value.face_image).toBe(true)
    expect(progressBySlot.value.face_image).toBe(60)

    secondXhr.onload?.()

    const secondResult = await secondPromise
    expect(secondResult.objectKey).toBe('uploads/second.png')
    expect(uploadingSlots.value.face_image).toBe(false)
    expect(progressBySlot.value.face_image).toBe(0)
    expect(messageSuccessMock).toHaveBeenCalledTimes(1)
  })
})
