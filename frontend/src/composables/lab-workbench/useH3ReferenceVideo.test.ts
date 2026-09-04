// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useH3ReferenceVideo } from './useH3ReferenceVideo'

const messageMock = vi.hoisted(() => ({ warning: vi.fn() }))
vi.mock('ant-design-vue', () => ({ message: messageMock }))

describe('useH3ReferenceVideo', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:motion'),
      revokeObjectURL: vi.fn(),
    })
  })

  it('uploads one reference video when its duration is at most 40 seconds', async () => {
    const uploadFile = vi.fn(async () => 'web_uploads/7/motion.mp4')
    const video = useH3ReferenceVideo({
      uploadFile,
      t: key => key,
      readDuration: vi.fn(async () => 40),
    })
    const file = new File(['motion'], 'motion.mp4', { type: 'video/mp4' })

    await video.beforeUploadReferenceVideo(file)

    expect(video.referenceVideo.value).toEqual({
      key: 'web_uploads/7/motion.mp4',
      preview: 'blob:motion',
      name: 'motion.mp4',
      durationSeconds: 40,
    })
    expect(uploadFile).toHaveBeenCalledWith(file, {
      maxSizeBytes: 40 * 1024 * 1024,
      maxSizeLabel: 'lab.workbench.minimax_h3_reference_video_size',
    })
  })

  it('rejects videos longer than 40 seconds before upload', async () => {
    const uploadFile = vi.fn()
    const video = useH3ReferenceVideo({
      uploadFile,
      t: key => key,
      readDuration: vi.fn(async () => 40.01),
    })

    await video.beforeUploadReferenceVideo(
      new File(['motion'], 'motion.mp4', { type: 'video/mp4' }),
    )

    expect(uploadFile).not.toHaveBeenCalled()
    expect(video.referenceVideo.value).toBeNull()
    expect(messageMock.warning).toHaveBeenCalledWith(
      'lab.workbench.validation.minimax_h3_reference_video_too_long',
    )
  })
})
