import { ref, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'

import {
  DEFAULT_FACE_VIDEO_RESOLUTION,
  EDIT_LORA_DEFAULT_STRENGTHS,
  getDefaultVideoLoraSelection,
  resolveLabModeIdFromTaskType,
  type LabUploadPreviewKind,
  type LabUploadSlotId,
  type UnifiedLabModeId,
} from '@/features/generation/labModeConfig'
import {
  DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
  normalizeImageToVideoLoraSelection,
  normalizeLtxVideoLoraItems,
  normalizeWan22VideoV2DurationSeconds,
  normalizeWan22VideoV2ResolutionPreset,
  type LtxVideoLoraItem,
  type Wan22VideoV2ResolutionPreset,
} from '@/features/generation/imageToVideo'
import type { Wan22ChainEditMode } from '@/features/generation/wan22Chain'
import { resolveTemplateVideoApplyState } from '@/utils/templateVideoApplyState'
import type { TranslateFn } from './types'

type HydratedTemplateState = {
  notice: string
  warning: string
  promptLocked: boolean
  editSettingsLocked: boolean
  videoSettingsLocked: boolean
  applied: boolean
  sourcePostId: number | null
}

type UseLabTemplateHydrationOptions = {
  route: RouteLocationNormalizedLoaded
  loadApplyContext: () => any
  currentModeId: Ref<UnifiedLabModeId>
  prompt: Ref<string>
  selectedEditLora: Ref<string>
  customEditLoraStrength: Ref<number>
  selectedVideoLora: Ref<string>
  ltxLoraItems: Ref<LtxVideoLoraItem[]>
  selectedLtxLoraNames: Ref<string[]>
  negativePrompt: Ref<string>
  wan22ResolutionPreset: Ref<Wan22VideoV2ResolutionPreset>
  resolution: Ref<string>
  duration: Ref<string>
  resetFormState: (options?: { preserveMode?: boolean }) => void
  getDefaultResolutionForMode: (modeId: UnifiedLabModeId) => string
  applyWan22ChainPrefill: (mode: Wan22ChainEditMode, taskId: string) => Promise<boolean>
  applyLtxExtensionPrefill: (
    path?: string | null,
    url?: string | null,
    options?: { previousTaskId?: string | null; chainTaskIds?: unknown },
  ) => boolean
  applySlotTemplateTarget: (
    slotId: LabUploadSlotId,
    target: { objectKey: string; previewUrl?: string | null; name: string; previewKind: LabUploadPreviewKind },
  ) => void
  t: TranslateFn
}

const toPositiveNumber = (value: unknown): number | null => {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null
}

const resolveWan22RouteMode = (value: unknown): Wan22ChainEditMode | null => (
  value === 'extend' || value === 'regenerate' ? value : null
)

export function useLabTemplateHydration({
  route,
  loadApplyContext,
  currentModeId,
  prompt,
  selectedEditLora,
  customEditLoraStrength,
  selectedVideoLora,
  ltxLoraItems,
  selectedLtxLoraNames,
  negativePrompt,
  wan22ResolutionPreset,
  resolution,
  duration,
  resetFormState,
  getDefaultResolutionForMode,
  applyWan22ChainPrefill,
  applyLtxExtensionPrefill,
  applySlotTemplateTarget,
  t,
}: UseLabTemplateHydrationOptions) {
  const templateNotice = ref('')
  const templateWarning = ref('')
  const isTemplateApplied = ref(false)
  const isTemplatePromptLocked = ref(false)
  const isTemplateEditSettingsLocked = ref(false)
  const isTemplateVideoSettingsLocked = ref(false)
  const templateSourcePostId = ref<number | null>(null)

  const resetTemplateState = () => {
    templateNotice.value = ''
    templateWarning.value = ''
    isTemplateApplied.value = false
    isTemplatePromptLocked.value = false
    isTemplateEditSettingsLocked.value = false
    isTemplateVideoSettingsLocked.value = false
    templateSourcePostId.value = null
  }

  const buildImageTemplateState = (modeId: UnifiedLabModeId): HydratedTemplateState | null => {
    const ctx = loadApplyContext()
    if (!ctx || route.query.apply !== 'true') {
      return null
    }

    const rawTaskType = String(ctx.task_type ?? '')
    const sourcePostId = toPositiveNumber(ctx.source_post_id)
    const promptValue = typeof ctx.prompt === 'string' ? ctx.prompt : ''

    if (modeId === 'edit' && (rawTaskType === 'edit' || rawTaskType === 'img2img_lora')) {
      prompt.value = promptValue
      selectedEditLora.value = typeof ctx.lora_name === 'string' ? ctx.lora_name : ''
      customEditLoraStrength.value = toPositiveNumber(ctx.lora_strength)
        ?? (selectedEditLora.value ? (EDIT_LORA_DEFAULT_STRENGTHS[selectedEditLora.value] ?? 1) : 1)

      return {
        applied: true,
        promptLocked: promptValue.trim().length > 0,
        editSettingsLocked: !!selectedEditLora.value,
        videoSettingsLocked: false,
        notice: selectedEditLora.value
          ? t('template_apply.image_prompt.template_notice_lora')
          : t('template_apply.image_prompt.template_notice_image'),
        warning: '',
        sourcePostId,
      }
    }

    if (modeId === 'i2i_pro' && rawTaskType === 'i2i_pro') {
      prompt.value = promptValue
      return {
        applied: true,
        promptLocked: promptValue.trim().length > 0,
        editSettingsLocked: false,
        videoSettingsLocked: false,
        notice: t('template_apply.image_prompt.template_notice_i2i'),
        warning: '',
        sourcePostId,
      }
    }

    if (modeId === 'i2i_draw' && rawTaskType === 'i2i_draw') {
      prompt.value = promptValue
      return {
        applied: true,
        promptLocked: promptValue.trim().length > 0,
        editSettingsLocked: false,
        videoSettingsLocked: false,
        notice: t('template_apply.image_prompt.template_notice_image'),
        warning: '',
        sourcePostId,
      }
    }

    return null
  }

  const hydrateFromRoute = () => {
    resetFormState({ preserveMode: true })

    const templateContext = route.query.apply === 'true' ? loadApplyContext() : null
    const nextModeId = resolveLabModeIdFromTaskType(
      templateContext ? String(templateContext.task_type ?? '') : String(route.query.type ?? ''),
    )

    currentModeId.value = nextModeId
    resolution.value = getDefaultResolutionForMode(nextModeId)

    if (nextModeId === 'wan22_video_v2' || nextModeId === 'custom_video') {
      const wan22Mode = resolveWan22RouteMode(route.query.wan22_mode)
      const wan22TaskId = typeof route.query.wan22_task_id === 'string'
        ? route.query.wan22_task_id
        : ''
      if (wan22Mode && wan22TaskId) {
        void applyWan22ChainPrefill(wan22Mode, wan22TaskId)
        return
      }
      if (nextModeId === 'wan22_video_v2' && !templateContext) {
        return
      }
    }

    if ((nextModeId === 'custom_video' || nextModeId === 'wan22_video_v2') && templateContext) {
      const rawTemplateTaskType = String(templateContext.task_type ?? '')
      const templateTaskType: 'custom_video' | 'video_lora' | 'wan22_video_v2' = nextModeId === 'wan22_video_v2'
        ? 'wan22_video_v2'
        : rawTemplateTaskType === 'video_lora' ? 'video_lora' : 'custom_video'
      const templateState = resolveTemplateVideoApplyState(templateContext, templateTaskType)
      if (templateState) {
        prompt.value = templateState.prompt ?? ''
        if (nextModeId === 'wan22_video_v2') {
          negativePrompt.value = templateState.negativePrompt || DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT
        }
        selectedVideoLora.value = templateState.loraName ?? getDefaultVideoLoraSelection()
        wan22ResolutionPreset.value = normalizeWan22VideoV2ResolutionPreset(templateState.resolution)
        duration.value = normalizeWan22VideoV2DurationSeconds(templateState.duration)
        templateNotice.value = templateState.templateApplyNotice
        templateWarning.value = templateState.templateSettingsWarning
        isTemplateApplied.value = templateState.isTemplateApplied
        isTemplatePromptLocked.value = templateState.isTemplatePromptLocked
        isTemplateVideoSettingsLocked.value = templateState.isTemplateVideoSettingsLocked
        templateSourcePostId.value = templateState.sourcePostId
      }
      return
    }

    if (nextModeId === 'ltx_video' && templateContext) {
      const templateState = resolveTemplateVideoApplyState(templateContext, 'ltx_video')
      if (templateState) {
        prompt.value = templateState.prompt ?? ''
        selectedVideoLora.value = normalizeImageToVideoLoraSelection(templateState.loraName)
        ltxLoraItems.value = normalizeLtxVideoLoraItems(templateState.loraItems)
        selectedLtxLoraNames.value = ltxLoraItems.value.map(item => item.name)
        resolution.value = templateState.resolution ?? getDefaultResolutionForMode('ltx_video')
        duration.value = templateState.duration ?? '5'
        templateNotice.value = templateState.templateApplyNotice
        templateWarning.value = templateState.templateSettingsWarning
        isTemplateApplied.value = templateState.isTemplateApplied
        isTemplatePromptLocked.value = templateState.isTemplatePromptLocked
        isTemplateVideoSettingsLocked.value = templateState.isTemplateVideoSettingsLocked
        templateSourcePostId.value = templateState.sourcePostId
      }
      return
    }

    if (nextModeId === 'ltx_video') {
      const ltxExtensionKey = typeof route.query.ltx_extend_key === 'string'
        ? route.query.ltx_extend_key
        : ''
      if (ltxExtensionKey) {
        const ltxExtensionUrl = typeof route.query.ltx_extend_url === 'string'
          ? route.query.ltx_extend_url
          : ''
        const ltxExtensionTaskId = typeof route.query.ltx_extend_task_id === 'string'
          ? route.query.ltx_extend_task_id
          : ''
        if (applyLtxExtensionPrefill(ltxExtensionKey, ltxExtensionUrl, {
          previousTaskId: ltxExtensionTaskId,
          chainTaskIds: route.query.ltx_chain_task_ids,
        })) {
          message.success(t('lab.workbench.ltx_extension_loaded'))
        }
        return
      }
    }

    if ((nextModeId === 'face_swap' || nextModeId === 'face_video') && templateContext) {
      const rawTaskType = String(templateContext.task_type ?? '')
      const targetSlotId = nextModeId === 'face_video' ? 'target_video' : 'target_image'
      if (rawTaskType === nextModeId && templateContext.input_file) {
        applySlotTemplateTarget(targetSlotId, {
          objectKey: String(templateContext.input_file),
          previewUrl: typeof templateContext.input_file_url === 'string'
            ? templateContext.input_file_url
            : null,
          name: t(nextModeId === 'face_video'
            ? 'lab.workbench.upload_slots.target_video'
            : 'lab.workbench.upload_slots.target_image'),
          previewKind: nextModeId === 'face_video' ? 'video' : 'image',
        })
        isTemplateApplied.value = true
        templateNotice.value = t(nextModeId === 'face_video'
          ? 'lab.workbench.template_notices.face_video'
          : 'lab.workbench.template_notices.face_swap')
        templateSourcePostId.value = toPositiveNumber(templateContext.source_post_id)
        if (nextModeId === 'face_video' && templateContext.width != null) {
          resolution.value = String(templateContext.width) === '1024' ? '1024' : DEFAULT_FACE_VIDEO_RESOLUTION
        }
      }
      return
    }

    const imageTemplateState = buildImageTemplateState(nextModeId)
    if (imageTemplateState) {
      templateNotice.value = imageTemplateState.notice
      templateWarning.value = imageTemplateState.warning
      isTemplateApplied.value = imageTemplateState.applied
      isTemplatePromptLocked.value = imageTemplateState.promptLocked
      isTemplateEditSettingsLocked.value = imageTemplateState.editSettingsLocked
      isTemplateVideoSettingsLocked.value = imageTemplateState.videoSettingsLocked
      templateSourcePostId.value = imageTemplateState.sourcePostId
    }
  }

  return {
    templateNotice,
    templateWarning,
    isTemplateApplied,
    isTemplatePromptLocked,
    isTemplateEditSettingsLocked,
    isTemplateVideoSettingsLocked,
    templateSourcePostId,
    resetTemplateState,
    hydrateFromRoute,
  }
}
