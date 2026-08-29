// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useH3ReferenceAudio } from './useH3ReferenceAudio'

describe('useH3ReferenceAudio', () => {
  beforeEach(() => {
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:voice'),
      revokeObjectURL: vi.fn(),
    })
  })

  it('keeps exactly one uploaded voice and revokes it on removal', async () => {
    const uploadFile = vi.fn(async () => 'web_uploads/7/voice.m4a')
    const audio = useH3ReferenceAudio({ uploadFile, t: key => key })
    const file = new File(['voice'], 'voice.m4a', { type: 'audio/mp4' })

    await audio.beforeUploadReferenceAudio(file)

    expect(audio.referenceAudio.value).toEqual({
      key: 'web_uploads/7/voice.m4a',
      preview: 'blob:voice',
      name: 'voice.m4a',
    })
    expect(uploadFile).toHaveBeenCalledWith(file, {
      maxSizeBytes: 20 * 1024 * 1024,
      maxSizeLabel: 'lab.workbench.minimax_h3_reference_audio_size',
    })

    audio.clearReferenceAudio()
    expect(audio.referenceAudio.value).toBeNull()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:voice')
  })
})
