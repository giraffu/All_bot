// @vitest-environment jsdom

import { describe, expect, it } from 'vitest'

import {
  SCAIL2_VIDEO_UPLOAD_MAX_SIZE_BYTES,
  SCAIL2_VIDEO_UPLOAD_MAX_SIZE_LABEL,
} from './useLabWorkbench'

describe('useLabWorkbench SCAIL-2 upload limits', () => {
  it('limits SCAIL-2 motion videos to 40MB in the browser', () => {
    expect(SCAIL2_VIDEO_UPLOAD_MAX_SIZE_BYTES).toBe(40 * 1024 * 1024)
    expect(SCAIL2_VIDEO_UPLOAD_MAX_SIZE_LABEL).toBe('40MB')
  })
})
