import { message } from 'ant-design-vue'
import type { Ref } from 'vue'

import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import { buildSwapTaskPayload } from '@/features/generation/buildSwapTaskPayload'
import {
  getImageToVideoPayloadLoraName,
  getImageToVideoPayloadLoraStrength,
  getImageToVideoRequestTaskType,
  normalizeWan22VideoV2DurationSeconds,
  type LtxVideoLoraItem,
  type Wan22VideoV2ResolutionPreset,
} from '@/features/generation/imageToVideo'
import type { LabModeConfig, LabUploadSlotId } from '@/features/generation/labModeConfig'
import { isScail2ModeId } from './modeHelpers'
import type {
  LabAssetUploadSlot,
  SubmitTaskFn,
  TranslateFn,
  UploadedReference,
  UploadedSlotAsset,
} from './types'

type UseLabSubmitPayloadOptions = {
  currentMode: Ref<LabModeConfig>
  hasStructuredUploadSlots: Ref<boolean>
  assetUploadSlots: Ref<LabAssetUploadSlot[]>
  uploadedReferences: Ref<UploadedReference[]>
  uploadedSlotAssets: Ref<Partial<Record<LabUploadSlotId, UploadedSlotAsset>>>
  prompt: Ref<string>
  selectedEditLora: Ref<string>
  customEditLoraStrength: Ref<number>
  selectedVideoLora: Ref<string>
  ltxLoraItems: Ref<LtxVideoLoraItem[]>
  negativePrompt: Ref<string>
  wan22ResolutionPreset: Ref<Wan22VideoV2ResolutionPreset>
  resolution: Ref<string>
  duration: Ref<string>
  isTemplateApplied: Ref<boolean>
  isTemplatePromptLocked: Ref<boolean>
  templateSourcePostId: Ref<number | null>
  wan22PrevTaskId: Ref<string | null>
  wan22ChainTaskIds: Ref<string[]>
  ltxPrevTaskId: Ref<string | null>
  ltxChainTaskIds: Ref<string[]>
  submitTask: SubmitTaskFn
  setSubmittedTaskId: (taskId: string | null) => void
  t: TranslateFn
}

export function useLabSubmitPayload({
  currentMode,
  hasStructuredUploadSlots,
  assetUploadSlots,
  uploadedReferences,
  uploadedSlotAssets,
  prompt,
  selectedEditLora,
  customEditLoraStrength,
  selectedVideoLora,
  ltxLoraItems,
  negativePrompt,
  wan22ResolutionPreset,
  resolution,
  duration,
  isTemplateApplied,
  isTemplatePromptLocked,
  templateSourcePostId,
  wan22PrevTaskId,
  wan22ChainTaskIds,
  ltxPrevTaskId,
  ltxChainTaskIds,
  submitTask,
  setSubmittedTaskId,
  t,
}: UseLabSubmitPayloadOptions) {
  const submitAndTrack = async (payload: Parameters<SubmitTaskFn>[0]) => {
    const taskId = await submitTask(payload, t(currentMode.value.titleKey))
    if (taskId) {
      setSubmittedTaskId(taskId)
    }
  }

  const handleSubmit = async () => {
    if (hasStructuredUploadSlots.value && !assetUploadSlots.value.every(slot => !slot.required || !!slot.item?.key)) {
      message.warning(t('lab.workbench.validation.upload_slots_required'))
      return
    }

    if (currentMode.value.supportsUpload && uploadedReferences.value.length === 0) {
      message.warning(t('lab.workbench.validation.upload_first'))
      return
    }

    if (currentMode.value.promptRequired && !isTemplatePromptLocked.value && prompt.value.trim().length === 0) {
      message.warning(t('lab.workbench.validation.prompt_required'))
      return
    }

    if (isScail2ModeId(currentMode.value.id)) {
      const referenceImage = uploadedSlotAssets.value.reference_image?.key
      const motionVideo = uploadedSlotAssets.value.motion_video?.key

      if (!referenceImage || !motionVideo) {
        message.warning(t('lab.workbench.validation.upload_slots_required'))
        return
      }

      await submitAndTrack(buildGenerationTaskPayload({
        taskType: currentMode.value.taskType,
        images: [referenceImage, motionVideo],
        duration: Number(duration.value),
        prompt: prompt.value,
        negativePrompt: negativePrompt.value,
        promptTarget: 'inputs',
        isTemplate: false,
      }))
      return
    }

    if (currentMode.value.id === 'ltx_video_audio') {
      const inputVideo = uploadedSlotAssets.value.input_video?.key

      if (!inputVideo) {
        message.warning(t('lab.workbench.validation.upload_slots_required'))
        return
      }

      await submitAndTrack(buildGenerationTaskPayload({
        taskType: 'ltx_video',
        images: [inputVideo],
        prompt: prompt.value,
        promptTarget: 'inputs',
        resolution: resolution.value,
        duration: Number(duration.value),
        loraItems: ltxLoraItems.value,
        extraInputs: {
          ltx_mode: 'v2v_audio',
          video: inputVideo,
          extract_last_frame: true,
        },
        isTemplate: isTemplateApplied.value,
        sourcePostId: templateSourcePostId.value,
      }))
      return
    }

    if (currentMode.value.id === 'face_swap' || currentMode.value.id === 'face_video') {
      const faceImage = uploadedSlotAssets.value.face_image?.key
      const targetSlot = currentMode.value.id === 'face_video' ? 'target_video' : 'target_image'
      const targetAsset = uploadedSlotAssets.value[targetSlot]?.key

      if (!faceImage || !targetAsset) {
        message.warning(t('lab.workbench.validation.upload_slots_required'))
        return
      }

      await submitAndTrack(buildSwapTaskPayload({
        taskType: currentMode.value.id,
        faceImage,
        targetField: currentMode.value.id === 'face_video' ? 'target_video' : 'target_image',
        targetAsset,
        resolution: currentMode.value.id === 'face_video' ? Number(resolution.value) : undefined,
        isTemplate: isTemplateApplied.value,
        sourcePostId: templateSourcePostId.value,
      }))
      return
    }

    if (currentMode.value.id === 'custom_video' || currentMode.value.id === 'wan22_video_v2') {
      const taskType = currentMode.value.id === 'wan22_video_v2'
        ? 'wan22_video_v2'
        : getImageToVideoRequestTaskType(currentMode.value.taskType, selectedVideoLora.value)
      await submitAndTrack(buildGenerationTaskPayload({
        taskType,
        images: uploadedReferences.value.map(item => item.key),
        duration: Number(normalizeWan22VideoV2DurationSeconds(duration.value)),
        prompt: prompt.value,
        negativePrompt: negativePrompt.value,
        promptTarget: 'inputs',
        loraName: currentMode.value.id === 'custom_video'
          ? getImageToVideoPayloadLoraName(currentMode.value.taskType, selectedVideoLora.value)
          : undefined,
        extraInputs: {
          use_end_frame: uploadedReferences.value.length >= 2,
          resolution_preset: wan22ResolutionPreset.value,
          wan22_prev_task_id: wan22PrevTaskId.value,
          wan22_chain_task_ids: wan22ChainTaskIds.value,
        },
        isTemplate: isTemplateApplied.value,
        sourcePostId: templateSourcePostId.value,
      }))
      return
    }

    await submitAndTrack(buildGenerationTaskPayload({
      taskType: currentMode.value.taskType,
      images: uploadedReferences.value.map(item => item.key),
      prompt: prompt.value,
      promptTarget: currentMode.value.promptTarget,
      loraName: currentMode.value.id === 'edit'
        ? (selectedEditLora.value || undefined)
        : getImageToVideoPayloadLoraName(currentMode.value.taskType, selectedVideoLora.value),
      loraStrength: currentMode.value.id === 'edit' && selectedEditLora.value
        ? Number(customEditLoraStrength.value)
        : currentMode.value.id === 'ltx_video'
          ? getImageToVideoPayloadLoraStrength(currentMode.value.taskType, selectedVideoLora.value)
          : undefined,
      resolution: currentMode.value.id === 'ltx_video'
        ? resolution.value
        : undefined,
      duration: currentMode.value.id === 'ltx_video'
        ? Number(duration.value)
        : undefined,
      loraItems: currentMode.value.id === 'ltx_video' ? ltxLoraItems.value : undefined,
      extraInputs: currentMode.value.id === 'ltx_video'
        ? {
            ltx_mode: uploadedReferences.value.length >= 2 ? 'flf2v' : 'i2v',
            use_end_frame: uploadedReferences.value.length >= 2,
            extract_last_frame: true,
            ltx_prev_task_id: ltxPrevTaskId.value || undefined,
            ltx_chain_task_ids: ltxChainTaskIds.value.length > 0 ? ltxChainTaskIds.value : undefined,
          }
        : undefined,
      normalizeEditLoraTask: currentMode.value.id === 'edit',
      isTemplate: isTemplateApplied.value,
      sourcePostId: templateSourcePostId.value,
    }))
  }

  return { handleSubmit }
}
