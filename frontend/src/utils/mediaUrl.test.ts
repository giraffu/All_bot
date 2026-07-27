import { describe, expect, it } from 'vitest'

import { resolveMediaUrl } from './mediaUrl'

describe('resolveMediaUrl', () => {
  it('keeps absolute media URLs and rejects retired relative storage paths', () => {
    expect(resolveMediaUrl('https://r2.aivison.it.com/history/task/original.png')).toBe(
      'https://r2.aivison.it.com/history/task/original.png',
    )
    expect(resolveMediaUrl('blob:https://web.aivison.it.com/id')).toBe(
      'blob:https://web.aivison.it.com/id',
    )
    expect(resolveMediaUrl('bot-data/123/input.png')).toBe('')
    expect(resolveMediaUrl('comfyui-temp/result.mp4')).toBe('')
    expect(resolveMediaUrl('result.png')).toBe('')
  })
})
