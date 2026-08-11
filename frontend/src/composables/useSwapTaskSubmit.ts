import { message } from 'ant-design-vue'

import { buildSwapTaskPayload } from '@/features/generation/buildSwapTaskPayload'

type SwapTaskType = 'face_swap' | 'face_video'
type SwapTargetField = 'target_image' | 'target_video'

type UseSwapTaskSubmitOptions = {
  taskType: SwapTaskType
  taskTitle: string
  targetField: SwapTargetField
  getFaceAssetKey: () => string | null
  getTargetAssetKey: () => string | null
  getResolution?: () => number | undefined
  getIsTemplateApplied?: () => boolean
  getSourcePostId?: () => number | null
  warningMessage: string
  submitTask: (payload: unknown, taskTitle: string) => Promise<string | null>
  setSubmittedTaskId: (taskId: string | null) => void
  onSubmitted?: (taskId: string) => Promise<void> | void
}

export function useSwapTaskSubmit(options: UseSwapTaskSubmitOptions) {
  const handleGenerate = async () => {
    const faceAssetKey = options.getFaceAssetKey()
    const targetAssetKey = options.getTargetAssetKey()

    if (!faceAssetKey || !targetAssetKey) {
      message.warning(options.warningMessage)
      return
    }

    const payload = buildSwapTaskPayload({
      taskType: options.taskType,
      faceImage: faceAssetKey,
      targetField: options.targetField,
      targetAsset: targetAssetKey,
      resolution: options.getResolution?.(),
      isTemplate: options.getIsTemplateApplied?.() ?? false,
      sourcePostId: options.getSourcePostId?.() ?? null,
    })

    const taskId = await options.submitTask(payload, options.taskTitle)
    if (taskId) {
      options.setSubmittedTaskId(taskId)
      await options.onSubmitted?.(taskId)
    }
  }

  return {
    handleGenerate,
  }
}
