import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'
import { useTaskResult } from '@/composables/useTaskResult'
import { useTaskStream } from '@/composables/useTaskStream'
import { useUpload } from '@/composables/useUpload'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import {
  DEFAULT_LAB_MODE_ID,
  DEFAULT_VIDEO_DURATION,
  DEFAULT_VIDEO_RESOLUTION,
  EDIT_LORA_DEFAULT_STRENGTHS,
  EDIT_LORA_OPTIONS,
  LEGACY_LAB_MODES,
  type LabModeConfig,
  type UnifiedLabModeId,
  UNIFIED_LAB_MODES,
  VIDEO_DURATION_OPTIONS,
  VIDEO_RESOLUTION_OPTIONS,
  getDefaultVideoLoraSelection,
  getLabModeConfig,
  getVideoLoraOptions,
  resolveLabModeIdFromTaskType,
} from '@/features/generation/labModeConfig'
import {
  getImageToVideoRequestTaskType,
  getImageToVideoPayloadLoraName,
} from '@/features/generation/imageToVideo'
import { resolveTemplateVideoApplyState } from '@/utils/templateVideoApplyState'

type UploadedReference = {
  key: string
  preview: string
  name: string
}

type HydratedTemplateState = {
  notice: string
  warning: string
  promptLocked: boolean
  editSettingsLocked: boolean
  videoSettingsLocked: boolean
  applied: boolean
  sourcePostId: number | null
}

const DEFAULT_EDIT_LORA_STRENGTH = 1

const toPositiveNumber = (value: unknown): number | null => {
  const numeric = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null
}

export function useLabWorkbench() {
  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const { loadApplyContext, clearApplyContext } = useGalleryApplyContext()
  const { uploading, progress: uploadProgress, uploadFile } = useUpload()
  const { isSubmitting, submitTask } = useTaskStream()
  const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()

  const currentModeId = ref<UnifiedLabModeId>(DEFAULT_LAB_MODE_ID)
  const prompt = ref('')
  const uploadedReferences = ref<UploadedReference[]>([])
  const pendingUploads = ref(0)

  const selectedEditLora = ref('')
  const customEditLoraStrength = ref(DEFAULT_EDIT_LORA_STRENGTH)
  const selectedVideoLora = ref(getDefaultVideoLoraSelection())
  const resolution = ref(DEFAULT_VIDEO_RESOLUTION)
  const duration = ref(DEFAULT_VIDEO_DURATION)

  const templateNotice = ref('')
  const templateWarning = ref('')
  const isTemplateApplied = ref(false)
  const isTemplatePromptLocked = ref(false)
  const isTemplateEditSettingsLocked = ref(false)
  const isTemplateVideoSettingsLocked = ref(false)
  const templateSourcePostId = ref<number | null>(null)

  const currentMode = computed<LabModeConfig>(() => getLabModeConfig(currentModeId.value))
  const unifiedModes = UNIFIED_LAB_MODES
  const legacyModes = LEGACY_LAB_MODES
  const editLoraOptions = EDIT_LORA_OPTIONS
  const videoLoraOptions = getVideoLoraOptions()
  const videoResolutionOptions = VIDEO_RESOLUTION_OPTIONS
  const videoDurationOptions = VIDEO_DURATION_OPTIONS

  const hasReferences = computed(() => uploadedReferences.value.length > 0)
  const hasAdvancedOptions = computed(() => currentMode.value.supportsAdvancedOptions)

  const referenceTitle = computed(() =>
    currentMode.value.referenceTitleKey ? t(currentMode.value.referenceTitleKey) : '',
  )

  const uploadButtonLabel = computed(() => (
    currentMode.value.maxImages > 1 && uploadedReferences.value.length === 1
      ? t('lab.workbench.add_second_reference')
      : t('lab.workbench.add_reference')
  ))

  const cost = computed(() => {
    if (currentMode.value.id === 'edit') {
      return uploadedReferences.value.length >= 2 ? 6 : 2
    }

    if (currentMode.value.id === 'custom_video') {
      let baseCost = 6
      if (resolution.value === '720') baseCost = 18
      else if (resolution.value === '1024') baseCost = 36

      let multiplier = 1
      if (duration.value === '8') multiplier = 2
      else if (duration.value === '10') multiplier = 3
      return baseCost * multiplier
    }

    return currentMode.value.baseCost
  })

  const costHint = computed(() => {
    if (currentMode.value.id === 'edit') {
      return t('lab.workbench.cost_hints.edit')
    }

    if (currentMode.value.id === 'custom_video') {
      return t('lab.workbench.cost_hints.custom_video')
    }

    return ''
  })

  const canSubmit = computed(() => {
    const hasPrompt = isTemplatePromptLocked.value || prompt.value.trim().length > 0
    const hasRequiredUpload = !currentMode.value.supportsUpload || uploadedReferences.value.length > 0
    return hasPrompt && hasRequiredUpload && pendingUploads.value === 0 && !uploading.value
  })

  const isDirty = computed(() => (
    prompt.value.trim().length > 0
    || uploadedReferences.value.length > 0
    || selectedEditLora.value !== ''
    || selectedVideoLora.value !== getDefaultVideoLoraSelection()
    || resolution.value !== DEFAULT_VIDEO_RESOLUTION
    || duration.value !== DEFAULT_VIDEO_DURATION
    || isTemplateApplied.value
  ))

  const revokeReferencePreview = (previewUrl: string | null | undefined) => {
    if (previewUrl?.startsWith('blob:')) {
      URL.revokeObjectURL(previewUrl)
    }
  }

  const clearReferences = () => {
    uploadedReferences.value.forEach(item => revokeReferencePreview(item.preview))
    uploadedReferences.value = []
  }

  const resetTemplateState = () => {
    templateNotice.value = ''
    templateWarning.value = ''
    isTemplateApplied.value = false
    isTemplatePromptLocked.value = false
    isTemplateEditSettingsLocked.value = false
    isTemplateVideoSettingsLocked.value = false
    templateSourcePostId.value = null
  }

  const resetFormState = (options?: { preserveMode?: boolean }) => {
    clearReferences()
    prompt.value = ''
    selectedEditLora.value = ''
    customEditLoraStrength.value = DEFAULT_EDIT_LORA_STRENGTH
    selectedVideoLora.value = getDefaultVideoLoraSelection()
    resolution.value = DEFAULT_VIDEO_RESOLUTION
    duration.value = DEFAULT_VIDEO_DURATION
    resetTemplateState()

    if (!options?.preserveMode) {
      currentModeId.value = DEFAULT_LAB_MODE_ID
    }

    setSubmittedTaskId(null)
  }

  const handleRemoveReference = (index: number) => {
    const target = uploadedReferences.value[index]
    revokeReferencePreview(target?.preview)
    uploadedReferences.value.splice(index, 1)
  }

  watch(selectedEditLora, (nextValue) => {
    if (isTemplateEditSettingsLocked.value) {
      return
    }

    customEditLoraStrength.value = nextValue
      ? (EDIT_LORA_DEFAULT_STRENGTHS[nextValue] ?? DEFAULT_EDIT_LORA_STRENGTH)
      : DEFAULT_EDIT_LORA_STRENGTH
  })

  watch(resolution, (value) => {
    if (currentMode.value.id !== 'custom_video') {
      return
    }
    if (value === '1024' && duration.value === '10') {
      duration.value = '8'
    }
  })

  watch(duration, (value) => {
    if (currentMode.value.id !== 'custom_video') {
      return
    }
    if (value === '10' && resolution.value === '1024') {
      resolution.value = '720'
    }
  })

  const beforeUpload = async (file: File) => {
    if (uploadedReferences.value.length + pendingUploads.value >= currentMode.value.maxImages) {
      message.warning(
        t('template_apply.image_prompt.max_images_warning', {
          count: currentMode.value.maxImages,
        }),
      )
      return false
    }

    pendingUploads.value += 1
    try {
      const objectKey = await uploadFile(file)
      if (!objectKey) {
        return false
      }

      uploadedReferences.value.push({
        key: objectKey,
        preview: URL.createObjectURL(file),
        name: file.name,
      })
      return false
    } finally {
      pendingUploads.value -= 1
    }
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

    if (nextModeId === 'custom_video' && templateContext) {
      const templateState = resolveTemplateVideoApplyState(templateContext, String(templateContext.task_type ?? '') === 'video_lora' ? 'video_lora' : 'custom_video')
      if (templateState) {
        prompt.value = templateState.prompt ?? ''
        selectedVideoLora.value = templateState.loraName ?? getDefaultVideoLoraSelection()
        resolution.value = templateState.resolution ?? DEFAULT_VIDEO_RESOLUTION
        duration.value = templateState.duration ?? DEFAULT_VIDEO_DURATION
        templateNotice.value = templateState.templateApplyNotice
        templateWarning.value = templateState.templateSettingsWarning
        isTemplateApplied.value = templateState.isTemplateApplied
        isTemplatePromptLocked.value = templateState.isTemplatePromptLocked
        isTemplateVideoSettingsLocked.value = templateState.isTemplateVideoSettingsLocked
        templateSourcePostId.value = templateState.sourcePostId
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

  watch(
    () => [route.query.type, route.query.apply],
    hydrateFromRoute,
    { immediate: true },
  )

  const confirmSwitchIfNeeded = async () => {
    if (!isDirty.value) {
      return true
    }

    return new Promise<boolean>((resolve) => {
      Modal.confirm({
        title: t('lab.workbench.switch_confirm_title'),
        content: t('lab.workbench.switch_confirm_content'),
        okText: t('lab.workbench.switch_confirm_ok'),
        cancelText: t('lab.workbench.switch_confirm_cancel'),
        onOk: () => resolve(true),
        onCancel: () => resolve(false),
      })
    })
  }

  const selectMode = async (nextModeId: UnifiedLabModeId) => {
    if (nextModeId === currentModeId.value) {
      return
    }

    const confirmed = await confirmSwitchIfNeeded()
    if (!confirmed) {
      return
    }

    clearApplyContext()
    const targetRouteName = route.name === 'LabPreview' ? 'LabPreview' : 'CustomFeatures'
    await router.replace({
      name: targetRouteName,
      query: {
        type: getLabModeConfig(nextModeId).taskType,
      },
    })
  }

  const openLegacyMode = async (modeId: typeof LEGACY_LAB_MODES[number]['id']) => {
    const mode = getLabModeConfig(modeId)
    if (!mode.legacyRouteName) {
      return
    }

    await router.push({
      name: mode.legacyRouteName,
      query: {
        type: mode.taskType,
        title: t(mode.titleKey),
        cost: String(mode.baseCost),
      },
    })
  }

  const handleSubmit = async () => {
    if (currentMode.value.supportsUpload && uploadedReferences.value.length === 0) {
      message.warning(t('lab.workbench.validation.upload_first'))
      return
    }

    if (!isTemplatePromptLocked.value && prompt.value.trim().length === 0) {
      message.warning(t('lab.workbench.validation.prompt_required'))
      return
    }

    const payload = buildGenerationTaskPayload({
      taskType: currentMode.value.id === 'custom_video'
        ? getImageToVideoRequestTaskType(currentMode.value.taskType, selectedVideoLora.value)
        : currentMode.value.taskType,
      images: uploadedReferences.value.map(item => item.key),
      prompt: prompt.value,
      promptTarget: currentMode.value.promptTarget,
      loraName: currentMode.value.id === 'edit'
        ? (selectedEditLora.value || undefined)
        : getImageToVideoPayloadLoraName(currentMode.value.taskType, selectedVideoLora.value),
      loraStrength: currentMode.value.id === 'edit' && selectedEditLora.value
        ? Number(customEditLoraStrength.value)
        : undefined,
      resolution: currentMode.value.id === 'custom_video' ? Number(resolution.value) : undefined,
      duration: currentMode.value.id === 'custom_video' ? Number(duration.value) : undefined,
      normalizeEditLoraTask: currentMode.value.id === 'edit',
      isTemplate: isTemplateApplied.value,
      sourcePostId: templateSourcePostId.value,
    })

    const taskId = await submitTask(payload, t(currentMode.value.titleKey))
    if (taskId) {
      setSubmittedTaskId(taskId)
    }
  }

  const resetAfterResult = () => {
    resetFormState({ preserveMode: true })
  }

  onBeforeUnmount(() => {
    clearReferences()
  })

  return {
    unifiedModes,
    legacyModes,
    currentMode,
    currentModeId,
    prompt,
    uploadedReferences,
    uploadProgress,
    uploading,
    isSubmitting,
    currentTask,
    isImageUrl,
    downloadResult,
    selectMode,
    openLegacyMode,
    beforeUpload,
    handleRemoveReference,
    handleSubmit,
    resetAfterResult,
    cost,
    costHint,
    canSubmit,
    hasReferences,
    hasAdvancedOptions,
    referenceTitle,
    uploadButtonLabel,
    editLoraOptions,
    selectedEditLora,
    customEditLoraStrength,
    videoLoraOptions,
    selectedVideoLora,
    videoResolutionOptions,
    resolution,
    videoDurationOptions,
    duration,
    templateNotice,
    templateWarning,
    isTemplateApplied,
    isTemplatePromptLocked,
    isTemplateEditSettingsLocked,
    isTemplateVideoSettingsLocked,
  }
}
