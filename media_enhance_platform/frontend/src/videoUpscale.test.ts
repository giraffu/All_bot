import { describe, expect, it } from 'vitest'
import {
  VIDEO_UPSCALE_MAX_BYTES,
  VIDEO_UPSCALE_MAX_SECONDS,
  validateVideoSelection,
} from './videoUpscale'

describe('video upscale selection', () => {
  it('accepts supported videos inside the test-worker contract', () => {
    expect(
      validateVideoSelection(
        { type: 'video/mp4', size: VIDEO_UPSCALE_MAX_BYTES },
        VIDEO_UPSCALE_MAX_SECONDS,
      ),
    ).toBeNull()
  })

  it('rejects images, oversized files and videos longer than five seconds', () => {
    expect(validateVideoSelection({ type: 'image/png', size: 1 }, 1)).toBe(
      'video_only',
    )
    expect(
      validateVideoSelection(
        { type: 'video/mp4', size: VIDEO_UPSCALE_MAX_BYTES + 1 },
        1,
      ),
    ).toBe('video_too_large')
    expect(
      validateVideoSelection(
        { type: 'video/webm', size: 1 },
        VIDEO_UPSCALE_MAX_SECONDS + 0.01,
      ),
    ).toBe('video_too_long')
  })

  it('rejects unsupported video containers', () => {
    expect(validateVideoSelection({ type: 'video/x-msvideo', size: 1 }, 1)).toBe(
      'unsupported_video',
    )
  })
})
