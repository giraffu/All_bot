import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'
import { useTaskResult } from '@/composables/useTaskResult'
import { useTaskStream } from '@/composables/useTaskStream'
import { useUpload } from '@/composables/useUpload'
import { buildGenerationTaskPayload } from '@/features/generation/buildGenerationTaskPayload'
import { buildSwapTaskPayload } from '@/features/generation/buildSwapTaskPayload'
import {
  DEFAULT_FACE_VIDEO_RESOLUTION,
  DEFAULT_LAB_MODE_ID,
  DEFAULT_LTX_VIDEO_RESOLUTION,
  DEFAULT_VIDEO_DURATION,
  DEFAULT_VIDEO_RESOLUTION,
  EDIT_LORA_DEFAULT_STRENGTHS,
  EDIT_LORA_OPTIONS,
  FACE_VIDEO_RESOLUTION_OPTIONS,
  LEGACY_LAB_MODES,
  LTX_VIDEO_DURATION_OPTIONS,
  LTX_VIDEO_RESOLUTION_OPTIONS,
  type LabUploadPreviewKind,
  type LabUploadSlotId,
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
  buildDefaultLtxVideoLoraItem,
  DEFAULT_WAN22_VIDEO_V2_COST,
  DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
  DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET,
  getImageToVideoRequestTaskType,
  getImageToVideoPayloadLoraName,
  getImageToVideoPayloadLoraStrength,
  LTX_VIDEO_LORA_OPTIONS,
  normalizeImageToVideoLoraSelection,
  normalizeLtxVideoLoraItems,
  WAN22_VIDEO_V2_RESOLUTION_OPTIONS,
  type LtxVideoLoraItem,
  type Wan22VideoV2ResolutionPreset,
} from '@/features/generation/imageToVideo'
import { resolveTemplateVideoApplyState } from '@/utils/templateVideoApplyState'

type UploadedReference = {
  key: string
  preview: string
  name: string
}

type PendingReferenceUpload = UploadedReference & {
  uploading: true
}

type UploadedSlotAsset = UploadedReference & {
  previewKind: LabUploadPreviewKind
  uploading?: true
}

type LabAssetUploadSlot = {
  id: LabUploadSlotId
  label: string
  hint: string
  buttonLabel: string
  accept: string
  previewKind: LabUploadPreviewKind
  required: boolean
  item: (UploadedSlotAsset & { progress?: number }) | null
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
  const pendingReferenceUploads = ref<PendingReferenceUpload[]>([])
  const uploadedSlotAssets = ref<Partial<Record<LabUploadSlotId, UploadedSlotAsset>>>({})
  const pendingUploads = ref(0)

  const selectedEditLora = ref('')
  const customEditLoraStrength = ref(DEFAULT_EDIT_LORA_STRENGTH)
  const selectedVideoLora = ref(getDefaultVideoLoraSelection())
  const ltxLoraItems = ref<LtxVideoLoraItem[]>([])
  const selectedLtxLoraNames = ref<string[]>([])
  const negativePrompt = ref(DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT)
  const wan22ResolutionPreset = ref<Wan22VideoV2ResolutionPreset>(DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET)
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
  const videoResolutionOptions = computed(() => (
    currentMode.value.id === 'face_video'
      ? FACE_VIDEO_RESOLUTION_OPTIONS
      : currentMode.value.id === 'ltx_video'
        ? LTX_VIDEO_RESOLUTION_OPTIONS
        : VIDEO_RESOLUTION_OPTIONS
  ))
  const videoDurationOptions = computed(() => (
    currentMode.value.id === 'ltx_video' ? LTX_VIDEO_DURATION_OPTIONS : VIDEO_DURATION_OPTIONS
  ))
  const ltxLoraOptions = LTX_VIDEO_LORA_OPTIONS
  const wan22ResolutionOptions = WAN22_VIDEO_V2_RESOLUTION_OPTIONS

  const hasReferences = computed(() => uploadedReferences.value.length > 0)
  const hasAdvancedOptions = computed(() => currentMode.value.supportsAdvancedOptions)
  const hasStructuredUploadSlots = computed(() => (currentMode.value.uploadSlots?.length ?? 0) > 0)
  const displayedReferences = computed(() => [
    ...uploadedReferences.value,
    ...pendingReferenceUploads.value.map(item => ({
      ...item,
      progress: uploadProgress.value,
    })),
  ])
  const canUploadReference = computed(() => (
    currentMode.value.supportsUpload
    && uploadedReferences.value.length + pendingReferenceUploads.value.length < currentMode.value.maxImages
  ))

  const assetUploadSlots = computed<LabAssetUploadSlot[]>(() => (
    currentMode.value.uploadSlots?.map((slot) => {
      const item = uploadedSlotAssets.value[slot.id] ?? null
      return {
        id: slot.id,
        label: t(slot.labelKey),
        hint: t(slot.hintKey),
        buttonLabel: t(slot.buttonKey),
        accept: slot.accept,
        previewKind: slot.previewKind,
        required: slot.required,
        item: item
          ? {
              ...item,
              progress: item.uploading ? uploadProgress.value : undefined,
            }
          : null,
      }
    }) ?? []
  ))

  const referenceTitle = computed(() =>
    currentMode.value.referenceTitleKey ? t(currentMode.value.referenceTitleKey) : '',
  )

  const uploadButtonLabel = computed(() => (
    currentMode.value.id === 'wan22_video_v2' && uploadedReferences.value.length === 0
      ? t('lab.workbench.add_start_frame')
      : currentMode.value.id === 'wan22_video_v2' && uploadedReferences.value.length === 1
        ? t('lab.workbench.add_end_frame')
        : currentMode.value.maxImages > 1 && uploadedReferences.value.length === 1
      ? t('lab.workbench.add_second_reference')
      : t('lab.workbench.add_reference')
  ))

  const getDefaultResolutionForMode = (modeId: UnifiedLabModeId) => (
    modeId === 'face_video'
      ? DEFAULT_FACE_VIDEO_RESOLUTION
      : modeId === 'ltx_video'
        ? DEFAULT_LTX_VIDEO_RESOLUTION
        : DEFAULT_VIDEO_RESOLUTION
  )

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

    if (currentMode.value.id === 'face_video') {
      return resolution.value === '1024' ? 36 : 18
    }

    if (currentMode.value.id === 'ltx_video') {
      let multiplier = 1
      if (duration.value === '10') multiplier = 2
      else if (duration.value === '15') multiplier = 3
      else if (duration.value === '20') multiplier = 4
      return 10 * multiplier
    }

    if (currentMode.value.id === 'wan22_video_v2') {
      return WAN22_VIDEO_V2_RESOLUTION_OPTIONS.find(option => option.value === wan22ResolutionPreset.value)?.cost
        ?? DEFAULT_WAN22_VIDEO_V2_COST
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

    if (currentMode.value.id === 'face_video') {
      return t('lab.workbench.cost_hints.face_video')
    }

    if (currentMode.value.id === 'ltx_video') {
      return t('lab.workbench.cost_hints.ltx_video')
    }

    if (currentMode.value.id === 'wan22_video_v2') {
      return t('lab.workbench.cost_hints.wan22_video_v2')
    }

    return ''
  })

  const canSubmit = computed(() => {
    const hasPrompt = !currentMode.value.promptRequired || isTemplatePromptLocked.value || prompt.value.trim().length > 0
    const hasRequiredUpload = !currentMode.value.supportsUpload || uploadedReferences.value.length > 0
    const hasRequiredSlots = assetUploadSlots.value.every(slot => !slot.required || !!slot.item?.key)
    return hasPrompt && hasRequiredUpload && hasRequiredSlots && pendingUploads.value === 0 && !uploading.value
  })

  const isDirty = computed(() => (
    prompt.value.trim().length > 0
    || uploadedReferences.value.length > 0
    || Object.keys(uploadedSlotAssets.value).length > 0
    || selectedEditLora.value !== ''
    || selectedVideoLora.value !== getDefaultVideoLoraSelection()
    || selectedLtxLoraNames.value.length > 0
    || negativePrompt.value !== DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT
    || wan22ResolutionPreset.value !== DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET
    || resolution.value !== getDefaultResolutionForMode(currentModeId.value)
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
    pendingReferenceUploads.value.forEach(item => revokeReferencePreview(item.preview))
    uploadedReferences.value = []
    pendingReferenceUploads.value = []
  }

  const clearSlotAssets = () => {
    Object.values(uploadedSlotAssets.value).forEach(item => revokeReferencePreview(item?.preview))
    uploadedSlotAssets.value = {}
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
    clearSlotAssets()
    prompt.value = ''
    selectedEditLora.value = ''
    customEditLoraStrength.value = DEFAULT_EDIT_LORA_STRENGTH
    selectedVideoLora.value = getDefaultVideoLoraSelection()
    ltxLoraItems.value = []
    selectedLtxLoraNames.value = []
    negativePrompt.value = DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT
    wan22ResolutionPreset.value = DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET
    resolution.value = getDefaultResolutionForMode(options?.preserveMode ? currentModeId.value : DEFAULT_LAB_MODE_ID)
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

  const handleRemoveUploadSlot = (slotId: LabUploadSlotId) => {
    const target = uploadedSlotAssets.value[slotId]
    revokeReferencePreview(target?.preview)
    delete uploadedSlotAssets.value[slotId]
  }

  watch(selectedEditLora, (nextValue) => {
    if (isTemplateEditSettingsLocked.value) {
      return
    }

    customEditLoraStrength.value = nextValue
      ? (EDIT_LORA_DEFAULT_STRENGTHS[nextValue] ?? DEFAULT_EDIT_LORA_STRENGTH)
      : DEFAULT_EDIT_LORA_STRENGTH
  })

  const syncLtxLoraItems = (names: string[]) => {
    const uniqueNames = Array.from(new Set(names.filter(value => value && value !== '__none__'))).slice(0, 3)
    if (uniqueNames.length < names.filter(value => value && value !== '__none__').length) {
      message.warning(t('lab.workbench.validation.ltx_lora_limit'))
    }
    selectedLtxLoraNames.value = uniqueNames
    ltxLoraItems.value = uniqueNames
      .map((name) => {
        const existing = ltxLoraItems.value.find(item => item.name === name)
        return existing ?? buildDefaultLtxVideoLoraItem(name)
      })
      .filter((item): item is LtxVideoLoraItem => Boolean(item))
  }

  const removeLtxLoraItem = (name: string) => {
    syncLtxLoraItems(selectedLtxLoraNames.value.filter(item => item !== name))
  }

  const updateLtxLoraStrength = (name: string, strength: number | null) => {
    if (typeof strength !== 'number' || !Number.isFinite(strength)) {
      return
    }
    const nextStrength = Math.min(2, Math.max(0.1, Number(strength.toFixed(2))))
    ltxLoraItems.value = ltxLoraItems.value.map(item => (
      item.name === name
        ? { ...item, strength: nextStrength }
        : item
    ))
  }

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
    if (uploadedReferences.value.length + pendingReferenceUploads.value.length >= currentMode.value.maxImages) {
      message.warning(
        t('template_apply.image_prompt.max_images_warning', {
          count: currentMode.value.maxImages,
        }),
      )
      return false
    }

    pendingUploads.value += 1
    const pendingKey = `pending-${Date.now()}-${file.name}`
    const preview = URL.createObjectURL(file)
    let objectKey: string | null = null
    pendingReferenceUploads.value.push({
      key: pendingKey,
      preview,
      name: file.name,
      uploading: true,
    })

    try {
      objectKey = await uploadFile(file)
      if (!objectKey) {
        return false
      }

      uploadedReferences.value.push({
        key: objectKey,
        preview,
        name: file.name,
      })
      return false
    } finally {
      pendingReferenceUploads.value = pendingReferenceUploads.value.filter(item => item.key !== pendingKey)
      if (!objectKey) {
        revokeReferencePreview(preview)
      }
      pendingUploads.value -= 1
    }
  }

  const beforeUploadSlot = async (slotId: LabUploadSlotId, file: File) => {
    const slot = currentMode.value.uploadSlots?.find(item => item.id === slotId)
    if (!slot) {
      return false
    }

    pendingUploads.value += 1
    const preview = URL.createObjectURL(file)
    const pendingKey = `pending-${slotId}-${Date.now()}-${file.name}`
    let objectKey: string | null = null
    handleRemoveUploadSlot(slotId)
    uploadedSlotAssets.value[slotId] = {
      key: pendingKey,
      preview,
      name: file.name,
      previewKind: slot.previewKind,
      uploading: true,
    }

    try {
      objectKey = await uploadFile(file)
      if (!objectKey) {
        return false
      }

      uploadedSlotAssets.value[slotId] = {
        key: objectKey,
        preview,
        name: file.name,
        previewKind: slot.previewKind,
      }
      return false
    } finally {
      if (!objectKey && uploadedSlotAssets.value[slotId]?.key === pendingKey) {
        delete uploadedSlotAssets.value[slotId]
        revokeReferencePreview(preview)
      }
      pendingUploads.value -= 1
    }
  }

  const applySlotTemplateTarget = (
    slotId: LabUploadSlotId,
    target: { objectKey: string; previewUrl?: string | null; name: string; previewKind: LabUploadPreviewKind },
  ) => {
    handleRemoveUploadSlot(slotId)
    uploadedSlotAssets.value[slotId] = {
      key: target.objectKey,
      preview: target.previewUrl ?? '',
      name: target.name,
      previewKind: target.previewKind,
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
    resolution.value = getDefaultResolutionForMode(nextModeId)

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

    if (nextModeId === 'ltx_video' && templateContext) {
      const templateState = resolveTemplateVideoApplyState(templateContext, 'ltx_video')
      if (templateState) {
        prompt.value = templateState.prompt ?? ''
        selectedVideoLora.value = normalizeImageToVideoLoraSelection(templateState.loraName)
        ltxLoraItems.value = normalizeLtxVideoLoraItems(templateState.loraItems)
        selectedLtxLoraNames.value = ltxLoraItems.value.map(item => item.name)
        resolution.value = templateState.resolution ?? DEFAULT_LTX_VIDEO_RESOLUTION
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

    if (currentMode.value.id === 'face_swap' || currentMode.value.id === 'face_video') {
      const faceImage = uploadedSlotAssets.value.face_image?.key
      const targetSlot = currentMode.value.id === 'face_video' ? 'target_video' : 'target_image'
      const targetAsset = uploadedSlotAssets.value[targetSlot]?.key

      if (!faceImage || !targetAsset) {
        message.warning(t('lab.workbench.validation.upload_slots_required'))
        return
      }

      const payload = buildSwapTaskPayload({
        taskType: currentMode.value.id,
        faceImage,
        targetField: currentMode.value.id === 'face_video' ? 'target_video' : 'target_image',
        targetAsset,
        resolution: currentMode.value.id === 'face_video' ? Number(resolution.value) : undefined,
        isTemplate: isTemplateApplied.value,
        sourcePostId: templateSourcePostId.value,
      })

      const taskId = await submitTask(payload, t(currentMode.value.titleKey))
      if (taskId) {
        setSubmittedTaskId(taskId)
      }
      return
    }

    if (currentMode.value.id === 'wan22_video_v2') {
      const payload = buildGenerationTaskPayload({
        taskType: 'wan22_video_v2',
        images: uploadedReferences.value.map(item => item.key),
        duration: 5,
        prompt: prompt.value,
        negativePrompt: negativePrompt.value,
        promptTarget: 'inputs',
        extraInputs: {
          use_end_frame: uploadedReferences.value.length >= 2,
          resolution_preset: wan22ResolutionPreset.value,
          wan22_prev_task_id: null,
          wan22_chain_task_ids: [],
        },
      })

      const taskId = await submitTask(payload, t(currentMode.value.titleKey))
      if (taskId) {
        setSubmittedTaskId(taskId)
      }
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
        : currentMode.value.id === 'ltx_video'
          ? getImageToVideoPayloadLoraStrength(currentMode.value.taskType, selectedVideoLora.value)
        : undefined,
      resolution: currentMode.value.id === 'custom_video'
        ? Number(resolution.value)
        : currentMode.value.id === 'ltx_video'
          ? resolution.value
          : undefined,
      duration: currentMode.value.id === 'custom_video' || currentMode.value.id === 'ltx_video'
        ? Number(duration.value)
        : undefined,
      loraItems: currentMode.value.id === 'ltx_video' ? ltxLoraItems.value : undefined,
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
    clearSlotAssets()
  })

  return {
    unifiedModes,
    legacyModes,
    currentMode,
    currentModeId,
    prompt,
    uploadedReferences,
    displayedReferences,
    assetUploadSlots,
    canUploadReference,
    isSubmitting,
    currentTask,
    isImageUrl,
    downloadResult,
    selectMode,
    openLegacyMode,
    beforeUpload,
    beforeUploadSlot,
    handleRemoveReference,
    handleRemoveUploadSlot,
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
    ltxLoraOptions,
    selectedLtxLoraNames,
    ltxLoraItems,
    syncLtxLoraItems,
    removeLtxLoraItem,
    updateLtxLoraStrength,
    negativePrompt,
    wan22ResolutionOptions,
    wan22ResolutionPreset,
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
