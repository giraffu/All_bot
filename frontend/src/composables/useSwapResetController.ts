type UseSwapResetControllerOptions = {
  resetUploads: () => void
  clearSubmittedTask: () => void
  resetResolution?: () => void
  clearTemplateState?: () => void
}

export function useSwapResetController(options: UseSwapResetControllerOptions) {
  const resetSwapState = () => {
    options.resetUploads()
    options.clearSubmittedTask()
    options.resetResolution?.()
    options.clearTemplateState?.()
  }

  return {
    resetSwapState,
  }
}
