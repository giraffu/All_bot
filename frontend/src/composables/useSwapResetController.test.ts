import { describe, expect, it, vi } from 'vitest'
import { useSwapResetController } from '@/composables/useSwapResetController'

describe('useSwapResetController', () => {
  it('clears uploads, submitted task, and optional resolution together', () => {
    const resetUploads = vi.fn()
    const clearSubmittedTask = vi.fn()
    const resetResolution = vi.fn()
    const clearTemplateState = vi.fn()

    const { resetSwapState } = useSwapResetController({
      resetUploads,
      clearSubmittedTask,
      resetResolution,
      clearTemplateState,
    })

    resetSwapState()

    expect(resetUploads).toHaveBeenCalledTimes(1)
    expect(clearSubmittedTask).toHaveBeenCalledTimes(1)
    expect(resetResolution).toHaveBeenCalledTimes(1)
    expect(clearTemplateState).toHaveBeenCalledTimes(1)
  })
})
