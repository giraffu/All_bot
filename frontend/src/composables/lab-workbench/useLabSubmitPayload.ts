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
import type {
  LabModeConfig,
  LabUploadSlotId,
  MiniMaxH3AddonItem,
} from '@/features/generation/labModeConfig'
import { isScail2ModeId } from './modeHelpers'
import type {
  LabAssetUploadSlot,
  SubmitTaskFn,
  TranslateFn,
  UploadedReference,
  UploadedReferenceAudio,
  UploadedSlotAsset,
} from './types'

type UseLabSubmitPayloadOptions = {
  currentMode: Ref<LabModeConfig>
  hasStructuredUploadSlots: Ref<boolean>
  assetUploadSlots: Ref<LabAssetUploadSlot[]>
  uploadedReferences: Ref<UploadedReference[]>
  uploadedSlotAssets: Ref<Partial<Record<LabUploadSlotId, UploadedSlotAsset>>>
  prompt: Ref<string>
  audioPrompt?: Ref<string>
  selectedEditLora: Ref<string>
  customEditLoraStrength: Ref<number>
  selectedVideoLora: Ref<string>
  ltxLoraItems: Ref<LtxVideoLoraItem[]>
  negativePrompt: Ref<string>
  wan22ResolutionPreset: Ref<Wan22VideoV2ResolutionPreset>
  resolution: Ref<string>
  duration: Ref<string>
  selectedCharacterIds?: Ref<string[]>
  useT2VReferences?: Ref<boolean>
  environmentSource?: Ref<'official' | 'upload'>
  selectedEnvironmentId?: Ref<string>
  minimaxH3Mode?: Ref<'t2v' | 'i2v' | 'flf2v' | 'ref2v'>
  minimaxH3ResolutionPreset?: Ref<'preview' | 'small' | 'standard' | 'hd'>
  minimaxH3AspectRatio?: Ref<'16:9' | '9:16' | '1:1' | '4:3' | '3:4'>
  minimaxH3AddonItems?: Ref<MiniMaxH3AddonItem[]>
  minimaxH3ReferenceAudio?: Ref<UploadedReferenceAudio | null>
  isTemplateApplied: Ref<boolean>
  isTemplatePromptLocked: Ref<boolean>
  templateSourcePostId: Ref<number | null>
  wan22PrevTaskId: Ref<string | null>
  wan22ChainTaskIds: Ref<string[]>
  ltxPrevTaskId: Ref<string | null>
  ltxChainTaskIds: Ref<string[]>
  h3PrevTaskId?: Ref<string | null>
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
  audioPrompt,
  selectedEditLora,
  customEditLoraStrength,
  selectedVideoLora,
  ltxLoraItems,
  negativePrompt,
  wan22ResolutionPreset,
  resolution,
  duration,
  selectedCharacterIds,
  useT2VReferences,
  environmentSource,
  selectedEnvironmentId,
  minimaxH3Mode,
  minimaxH3ResolutionPreset,
  minimaxH3AspectRatio,
  minimaxH3AddonItems,
  minimaxH3ReferenceAudio,
  isTemplateApplied,
  isTemplatePromptLocked,
  templateSourcePostId,
  wan22PrevTaskId,
  wan22ChainTaskIds,
  ltxPrevTaskId,
  ltxChainTaskIds,
  h3PrevTaskId,
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

    if (currentMode.value.supportsUpload && !['ltx_t2v', 'minimax_h3'].includes(currentMode.value.id) && uploadedReferences.value.length === 0) {
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

    if (currentMode.value.id === 'ltx25_video_upscale') {
      const video = uploadedSlotAssets.value.target_video
      if (!video?.key) {
        message.warning(t('lab.workbench.validation.upload_slots_required'))
        return
      }
      if (
        typeof video.durationSeconds === 'number'
        && video.durationSeconds > 5.1
      ) {
        message.warning(t('lab.workbench.validation.ltx25_video_too_long'))
        return
      }
      await submitAndTrack(buildGenerationTaskPayload({
        taskType: 'ltx25_video_upscale',
        images: [video.key],
        duration: 5,
        prompt: prompt.value,
        promptTarget: 'inputs',
        isTemplate: false,
      }))
      return
    }

    if (currentMode.value.id === 'minimax_h3') {
      const isH3Extension = Boolean(h3PrevTaskId?.value)
      const mode = isH3Extension ? 'ref2v' : minimaxH3Mode?.value ?? 't2v'
      const images = uploadedReferences.value.map(item => item.key)
      const clientImages = h3PrevTaskId?.value
        ? uploadedReferences.value.filter(item => !item.locked).map(item => item.key)
        : images
      const expected = isH3Extension
        ? mode === 'ref2v'
          ? [0, 0]
          : mode === 'flf2v'
            ? [1, 1]
            : [-1, -1]
        : mode === 't2v'
        ? [0, 0]
        : mode === 'i2v'
          ? [1, 1]
          : mode === 'flf2v'
            ? [2, 2]
            : [1, 4]
      if (images.length < expected[0] || images.length > expected[1]) {
        message.warning(t('lab.workbench.validation.minimax_h3_images'))
        return
      }
      const aspectRatio = mode === 'i2v' || mode === 'flf2v'
        ? 'source'
        : minimaxH3AspectRatio?.value ?? '16:9'
      if (mode === 'flf2v') {
        const [first, last] = uploadedReferences.value
        if (first?.width && first.height && last?.width && last.height) {
          const firstRatio = first.width / first.height
          const lastRatio = last.width / last.height
          if (Math.abs(firstRatio - lastRatio) / firstRatio > 0.01) {
            message.warning(t('lab.workbench.validation.minimax_h3_frame_ratio'))
            return
          }
        }
      }
      await submitAndTrack(buildGenerationTaskPayload({
        taskType: `minimax_h3_${mode}`,
        images: mode === 'ref2v' ? [] : clientImages,
        duration: Number(duration.value),
        prompt: prompt.value,
        promptTarget: 'inputs',
        extraInputs: {
          resolution_preset: minimaxH3ResolutionPreset?.value ?? 'preview',
          aspect_ratio: aspectRatio,
          ...(h3PrevTaskId?.value
            ? { minimax_h3_prev_task_id: h3PrevTaskId.value }
            : {}),
          ...(!isH3Extension && (mode === 'i2v' || mode === 'flf2v')
            ? {
                source_width: uploadedReferences.value[0]?.width,
                source_height: uploadedReferences.value[0]?.height,
                end_source_width: uploadedReferences.value[1]?.width,
                end_source_height: uploadedReferences.value[1]?.height,
              }
            : {}),
          ...(mode === 'ref2v' && !isH3Extension
            ? {
                reference_refs: uploadedReferences.value.map(item => item.referenceRef ?? ({
                  source: 'upload' as const,
                  object_key: item.key,
                })),
                ...(minimaxH3ReferenceAudio?.value
                  ? {
                      reference_audio_ref: minimaxH3ReferenceAudio.value.referenceRef ?? {
                        source: 'upload' as const,
                        object_key: minimaxH3ReferenceAudio.value.key,
                      },
                    }
                  : {}),
              }
            : {}),
        },
        isTemplate: false,
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

    if (currentMode.value.id === 'ltx_t2v') {
      const characterIds = selectedCharacterIds?.value ?? []
      const usesCharacter = useT2VReferences?.value ?? characterIds.length > 0
      const usesOfficialEnvironment = environmentSource?.value === 'official'
      if (usesCharacter && (characterIds.length !== 2 || (usesOfficialEnvironment
        ? !selectedEnvironmentId?.value || uploadedReferences.value.length !== 0
        : uploadedReferences.value.length !== 1))) {
        message.warning(t('characters.msr_requires_two_and_background'))
        return
      }
      if (!usesCharacter && uploadedReferences.value.length > 0) {
        message.warning(t('characters.background_requires_two'))
        return
      }
      await submitAndTrack(buildGenerationTaskPayload({
        taskType: usesCharacter ? 'ltx_t2v_ic' : 'ltx_t2v',
        images: [],
        prompt: prompt.value,
        negativePrompt: negativePrompt.value,
        promptTarget: 'inputs',
        resolution: usesCharacter ? '768x448' : '1280x704',
        duration: Number(duration.value),
        extraInputs: {
          ...(usesCharacter
            ? {
                character_refs: characterIds.map((value) => {
                  const [source, id] = value.includes(':') ? value.split(':', 2) : ['private', value]
                  return { source, id }
                }),
                environment_ref: usesOfficialEnvironment
                  ? { source: 'official', id: selectedEnvironmentId?.value }
                  : { source: 'upload', object_key: uploadedReferences.value[0]?.key },
              }
            : {}),
          ...(audioPrompt?.value.trim() ? { audio_prompt: audioPrompt.value.trim() } : {}),
        },
      }))
      return
    }

    const uploadedReferenceKeys = uploadedReferences.value.map(item => item.key)

    const isLtxVideo = currentMode.value.id === 'ltx_video' || currentMode.value.id === 'ltx_video_v2'
    const isLtxVideoV2 = currentMode.value.id === 'ltx_video_v2'
    await submitAndTrack(buildGenerationTaskPayload({
      taskType: isLtxVideoV2 && uploadedReferenceKeys.length >= 2
        ? 'ltx_video_v2_flf2v'
        : currentMode.value.taskType,
      images: uploadedReferenceKeys,
      prompt: prompt.value,
      negativePrompt: isLtxVideo ? negativePrompt.value : undefined,
      promptTarget: currentMode.value.promptTarget,
      loraName: currentMode.value.id === 'edit'
        ? (selectedEditLora.value || undefined)
        : isLtxVideoV2
          ? undefined
          : getImageToVideoPayloadLoraName(currentMode.value.taskType, selectedVideoLora.value),
      loraStrength: currentMode.value.id === 'edit' && selectedEditLora.value
        ? Number(customEditLoraStrength.value)
        : currentMode.value.id === 'ltx_video'
          ? getImageToVideoPayloadLoraStrength(currentMode.value.taskType, selectedVideoLora.value)
          : undefined,
      resolution: isLtxVideo
        ? resolution.value
        : undefined,
      duration: isLtxVideo
        ? Number(duration.value)
        : undefined,
      loraItems: currentMode.value.id === 'ltx_video' ? ltxLoraItems.value : undefined,
      extraInputs: isLtxVideo
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
