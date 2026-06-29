import { describe, expect, it } from 'vitest'

import { resolveOriginalInputPreviews } from '@/utils/originalInputs'

const t = (key: string, params?: Record<string, unknown>) => (
  params?.count ? `${key}:${params.count}` : key
)

describe('resolveOriginalInputPreviews', () => {
  it('hides txt2img records even if legacy input fields exist', () => {
    expect(resolveOriginalInputPreviews({
      task_type: 'txt2img',
      input_file: 'uploads/reference.png',
      input_file_url: 'https://cdn.test/reference.png',
    }, t)).toEqual([])
  })

  it('labels Wan22 start and end frames in input order', () => {
    const previews = resolveOriginalInputPreviews({
      task_type: 'wan22_video_v2',
      input_files: ['uploads/start.png', 'uploads/end.png'],
      input_file_urls: ['https://cdn.test/start.png', 'https://cdn.test/end.png'],
    }, t)

    expect(previews.map((preview) => preview.label)).toEqual([
      'original_inputs.start_frame',
      'original_inputs.end_frame',
    ])
    expect(previews.map((preview) => preview.url)).toEqual([
      'https://cdn.test/start.png',
      'https://cdn.test/end.png',
    ])
  })

  it('labels LTX FLF2V execution alias start and end frames in input order', () => {
    const previews = resolveOriginalInputPreviews({
      task_type: 'ltx_video_flf2v',
      input_files: ['uploads/start.png', 'uploads/end.png'],
      input_file_urls: ['https://cdn.test/start.png', 'https://cdn.test/end.png'],
    }, t)

    expect(previews.map((preview) => preview.label)).toEqual([
      'original_inputs.start_frame',
      'original_inputs.end_frame',
    ])
    expect(previews.map((preview) => preview.url)).toEqual([
      'https://cdn.test/start.png',
      'https://cdn.test/end.png',
    ])
  })

  it('labels SCAIL-2 reference image and motion video', () => {
    const previews = resolveOriginalInputPreviews({
      task_type: 'scail2_action_transfer_long',
      input_file: 'uploads/reference.png|uploads/motion.mp4',
      input_file_urls: ['https://cdn.test/reference.png', 'https://cdn.test/motion.mp4'],
    }, t)

    expect(previews.map((preview) => preview.label)).toEqual([
      'original_inputs.reference_image',
      'original_inputs.motion_video',
    ])
    expect(previews.map((preview) => preview.mediaType)).toEqual(['image', 'video'])
  })
})
