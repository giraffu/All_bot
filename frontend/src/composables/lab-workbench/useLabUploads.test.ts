// @vitest-environment jsdom

import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getLabModeConfig, type UnifiedLabModeId } from '@/features/generation/labModeConfig'
import { useLabReferenceUploads } from './useLabReferenceUploads'
import {
  SCAIL2_VIDEO_UPLOAD_MAX_SIZE_BYTES,
  SCAIL2_VIDEO_UPLOAD_MAX_SIZE_LABEL,
  useLabSlotUploads,
} from './useLabSlotUploads'

const messageMock = vi.hoisted(() => ({
  warning: vi.fn(),
  info: vi.fn(),
}))

vi.mock('ant-design-vue', () => ({
  message: messageMock,
}))

const createObjectURL = vi.fn((file: File) => `blob:${file.name}`)
const revokeObjectURL = vi.fn()
const t = (key: string) => key

beforeEach(() => {
  vi.clearAllMocks()
  Object.defineProperty(URL, 'createObjectURL', {
    configurable: true,
    value: createObjectURL,
  })
  Object.defineProperty(URL, 'revokeObjectURL', {
    configurable: true,
    value: revokeObjectURL,
  })
})

const currentModeRef = (modeId: UnifiedLabModeId) => {
  const currentModeId = ref(modeId)
  return computed(() => getLabModeConfig(currentModeId.value))
}

describe('useLabReferenceUploads', () => {
  it('uploads references and removes the pending item after success', async () => {
    const uploadFile = vi.fn(async (file: File) => `uploads/${file.name}`)
    const uploads = useLabReferenceUploads({
      currentMode: currentModeRef('edit'),
      uploadProgress: ref(30),
      uploadFile,
      t,
    })

    await uploads.beforeUpload(new File(['image'], 'base.png', { type: 'image/png' }))

    expect(uploadFile).toHaveBeenCalledOnce()
    expect(uploads.pendingReferenceUploadCount.value).toBe(0)
    expect(uploads.pendingReferenceUploads.value).toEqual([])
    expect(uploads.uploadedReferences.value).toEqual([{
      key: 'uploads/base.png',
      preview: 'blob:base.png',
      name: 'base.png',
    }])
    expect(revokeObjectURL).not.toHaveBeenCalled()
  })

  it('revokes the preview when upload fails before creating a stored reference', async () => {
    const uploadFile = vi.fn(async () => null)
    const uploads = useLabReferenceUploads({
      currentMode: currentModeRef('edit'),
      uploadProgress: ref(0),
      uploadFile,
      t,
    })

    await uploads.beforeUpload(new File(['image'], 'broken.png', { type: 'image/png' }))

    expect(uploads.pendingReferenceUploadCount.value).toBe(0)
    expect(uploads.uploadedReferences.value).toEqual([])
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:broken.png')
  })
})

describe('useLabSlotUploads', () => {
  it('limits SCAIL-2 motion video uploads to 40MB', async () => {
    const video = new File(['video'], 'motion.mp4', { type: 'video/mp4' })
    const uploadFile = vi.fn(async (file: File) => `uploads/${file.name}`)
    const uploads = useLabSlotUploads({
      currentMode: currentModeRef('scail2_action_transfer'),
      uploadProgress: ref(0),
      uploadFile,
      t,
    })

    await uploads.beforeUploadSlot('motion_video', video)

    expect(uploadFile).toHaveBeenCalledWith(video, {
      maxSizeBytes: SCAIL2_VIDEO_UPLOAD_MAX_SIZE_BYTES,
      maxSizeLabel: SCAIL2_VIDEO_UPLOAD_MAX_SIZE_LABEL,
    })
    expect(uploads.uploadedSlotAssets.value.motion_video?.key).toBe('uploads/motion.mp4')
  })

  it('limits LTX audio video uploads to 40MB', async () => {
    const video = new File(['video'], 'input.mp4', { type: 'video/mp4' })
    const uploadFile = vi.fn(async (file: File) => `uploads/${file.name}`)
    const uploads = useLabSlotUploads({
      currentMode: currentModeRef('ltx_video_audio'),
      uploadProgress: ref(0),
      uploadFile,
      t,
    })

    await uploads.beforeUploadSlot('input_video', video)

    expect(uploadFile).toHaveBeenCalledWith(video, {
      maxSizeBytes: SCAIL2_VIDEO_UPLOAD_MAX_SIZE_BYTES,
      maxSizeLabel: SCAIL2_VIDEO_UPLOAD_MAX_SIZE_LABEL,
    })
  })

  it('does not pass video size limits to image-only structured slots', async () => {
    const file = new File(['image'], 'face.png', { type: 'image/png' })
    const uploadFile = vi.fn(async (uploaded: File) => `uploads/${uploaded.name}`)
    const uploads = useLabSlotUploads({
      currentMode: currentModeRef('face_swap'),
      uploadProgress: ref(0),
      uploadFile,
      t,
    })

    await uploads.beforeUploadSlot('face_image', file)

    expect(uploadFile).toHaveBeenCalledWith(file, undefined)
  })

  it('cleans a pending slot preview after failed upload', async () => {
    const uploadFile = vi.fn(async () => null)
    const uploads = useLabSlotUploads({
      currentMode: currentModeRef('face_swap'),
      uploadProgress: ref(0),
      uploadFile,
      t,
    })

    await uploads.beforeUploadSlot('face_image', new File(['image'], 'failed.png', { type: 'image/png' }))

    expect(uploads.pendingSlotUploadCount.value).toBe(0)
    expect(uploads.uploadedSlotAssets.value.face_image).toBeUndefined()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:failed.png')
  })
})
