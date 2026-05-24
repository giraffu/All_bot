type SwapApplyContext = {
  task_type?: string
  input_file?: string | null
  input_file_url?: string | null
  source_post_id?: number | string | null
  width?: number | string | null
}

type UseLegacySwapApplyOptions = {
  routeApplyEnabled: boolean
  loadApplyContext: () => SwapApplyContext | null | undefined
  expectedTaskType: 'face_swap' | 'face_video'
  applySecondaryTemplateTarget: (target: {
    objectKey: string
    previewUrl?: string | null
  }) => void
  setTemplateApplied: (value: boolean) => void
  setSourcePostId: (value: number | null) => void
  setResolution?: (value: string) => void
}

export function useLegacySwapApply(options: UseLegacySwapApplyOptions) {
  const initializeLegacySwapApply = () => {
    if (!options.routeApplyEnabled) {
      return
    }

    const context = options.loadApplyContext()
    if (!context || context.task_type !== options.expectedTaskType || !context.input_file) {
      return
    }

    options.applySecondaryTemplateTarget({
      objectKey: context.input_file,
      previewUrl: context.input_file_url || null,
    })

    if (context.source_post_id != null) {
      options.setSourcePostId(Number(context.source_post_id))
    }

    if (options.setResolution && context.width != null) {
      options.setResolution(String(context.width))
    }

    options.setTemplateApplied(true)
  }

  return {
    initializeLegacySwapApply,
  }
}
