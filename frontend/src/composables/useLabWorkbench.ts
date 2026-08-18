import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useGalleryApplyContext } from '@/composables/useGalleryApplyContext'
import { useTaskResult } from '@/composables/useTaskResult'
import { useTaskSubmission } from '@/composables/useTaskSubmission'
import { useUpload } from '@/composables/useUpload'
import { useTasksStore } from '@/stores/tasks'
import type { PromptOptimizationOriginDraft } from '@/stores/taskStoreTypes'
import api from '@/api'
import {
  DEFAULT_LAB_MODE_ID,
  DEFAULT_VIDEO_DURATION,
  EDIT_LORA_DEFAULT_STRENGTHS,
  EDIT_LORA_OPTIONS,
  FACE_VIDEO_RESOLUTION_OPTIONS,
  LTX_T2V_IC_RESOLUTION_OPTIONS,
  LTX_VIDEO_DURATION_OPTIONS,
  LTX_VIDEO_RESOLUTION_OPTIONS,
  MINIMAX_H3_ADDON_OPTIONS,
  type LabModeConfig,
  type MiniMaxH3AddonItem,
  type UnifiedLabModeId,
  UNIFIED_LAB_MODES,
  VIDEO_DURATION_OPTIONS,
  VIDEO_RESOLUTION_OPTIONS,
  getDefaultVideoLoraSelection,
  getLabModeConfig,
  getScail2VideoDurationOptionsForMotionVideo,
  getVideoLoraOptions,
} from '@/features/generation/labModeConfig'
import {
  buildDefaultLtxVideoLoraItem,
  DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT,
  DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET,
  LTX_VIDEO_LORA_OPTIONS,
  WAN22_VIDEO_V2_RESOLUTION_OPTIONS,
  type LtxVideoLoraItem,
  type Wan22VideoV2ResolutionPreset,
} from '@/features/generation/imageToVideo'
import {
  DEFAULT_EDIT_LORA_STRENGTH,
  getDefaultResolutionForMode,
  getLabCostHintKey,
  getLabModeCost,
  isLtxLabModeId,
  isScail2ModeId,
} from './lab-workbench/modeHelpers'
import { useLabReferenceUploads } from './lab-workbench/useLabReferenceUploads'
import {
  SCAIL2_VIDEO_UPLOAD_MAX_SIZE_BYTES,
  SCAIL2_VIDEO_UPLOAD_MAX_SIZE_LABEL,
  useLabSlotUploads,
} from './lab-workbench/useLabSlotUploads'
import { useWan22ChainEditor } from './lab-workbench/useWan22ChainEditor'
import { useLtxChainEditor } from './lab-workbench/useLtxChainEditor'
import { useLabTemplateHydration } from './lab-workbench/useLabTemplateHydration'
import { useLabSubmitPayload } from './lab-workbench/useLabSubmitPayload'
import { usePromptOptimizer } from './lab-workbench/usePromptOptimizer'

export {
  SCAIL2_VIDEO_UPLOAD_MAX_SIZE_BYTES,
  SCAIL2_VIDEO_UPLOAD_MAX_SIZE_LABEL,
}

export function useLabWorkbench() {
  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const { loadApplyContext, clearApplyContext } = useGalleryApplyContext()
  const { uploading, progress: uploadProgress, uploadFile } = useUpload()
  const { isSubmitting, submitTask } = useTaskSubmission()
  const { currentTask, setSubmittedTaskId, isImageUrl, downloadResult } = useTaskResult()
  const tasksStore = useTasksStore()

  const currentModeId = ref<UnifiedLabModeId>(DEFAULT_LAB_MODE_ID)
  const prompt = ref('')
  const audioPrompt = ref('')
  const selectedEditLora = ref('')
  const customEditLoraStrength = ref(DEFAULT_EDIT_LORA_STRENGTH)
  const selectedVideoLora = ref(getDefaultVideoLoraSelection())
  const ltxLoraItems = ref<LtxVideoLoraItem[]>([])
  const selectedLtxLoraNames = ref<string[]>([])
  const negativePrompt = ref(DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT)
  const wan22ResolutionPreset = ref<Wan22VideoV2ResolutionPreset>(DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET)
  const resolution = ref(getDefaultResolutionForMode(DEFAULT_LAB_MODE_ID))
  const duration = ref(DEFAULT_VIDEO_DURATION)
  const selectedCharacterIds = ref<string[]>([])
  const useT2VReferences = ref(false)
  const environmentSource = ref<'official' | 'upload'>('official')
  const selectedEnvironmentId = ref('')
  const minimaxH3Mode = ref<'t2v' | 'i2v' | 'flf2v'>('t2v')
  const minimaxH3ResolutionPreset = ref<'preview' | 'small' | 'standard' | 'hd'>('preview')
  const minimaxH3AspectRatio = ref<'16:9' | '9:16' | '1:1' | '4:3' | '3:4'>('16:9')
  const minimaxH3ReferenceDescriptions = ref<string[]>(['', '', '', ''])
  const minimaxH3AddonNames = ref<string[]>([])
  const minimaxH3AddonItems = ref<MiniMaxH3AddonItem[]>([])
  const minimaxH3AddonOptions = MINIMAX_H3_ADDON_OPTIONS

  const currentMode = computed<LabModeConfig>(() => getLabModeConfig(currentModeId.value))
  const unifiedModes = UNIFIED_LAB_MODES
  const editLoraOptions = EDIT_LORA_OPTIONS
  const videoLoraOptions = getVideoLoraOptions()
  const ltxLoraOptions = LTX_VIDEO_LORA_OPTIONS
  const wan22ResolutionOptions = WAN22_VIDEO_V2_RESOLUTION_OPTIONS

  const references = useLabReferenceUploads({
    currentMode,
    uploadProgress,
    uploadFile,
    t,
  })
  const slots = useLabSlotUploads({
    currentMode,
    uploadProgress,
    uploadFile,
    t,
  })

  const capturePromptOptimizationDraft = (): PromptOptimizationOriginDraft => ({
    modeId: currentModeId.value,
    routeType: getLabModeConfig(currentModeId.value).taskType,
    prompt: prompt.value,
    duration: duration.value,
    uploadedReferences: references.uploadedReferences.value.map(item => ({ ...item })),
    settings: {
      resolution: resolution.value,
      selectedCharacterIds: [...selectedCharacterIds.value],
      useT2VReferences: useT2VReferences.value,
      environmentSource: environmentSource.value,
      selectedEnvironmentId: selectedEnvironmentId.value,
      minimaxH3Mode: minimaxH3Mode.value,
      minimaxH3ResolutionPreset: minimaxH3ResolutionPreset.value,
      minimaxH3AspectRatio: minimaxH3AspectRatio.value,
      minimaxH3ReferenceDescriptions: [...minimaxH3ReferenceDescriptions.value],
      minimaxH3AddonNames: [...minimaxH3AddonNames.value],
      minimaxH3AddonItems: minimaxH3AddonItems.value.map(item => ({ ...item })),
      selectedLtxLoraNames: [...selectedLtxLoraNames.value],
      ltxLoraItems: ltxLoraItems.value.map(item => ({ ...item })),
    },
  })

  const restorePromptOptimizationDraft = async (draft: PromptOptimizationOriginDraft) => {
    currentModeId.value = draft.modeId as UnifiedLabModeId
    prompt.value = draft.prompt
    duration.value = draft.duration
    const restoredReferences = await Promise.all(
      draft.uploadedReferences.map(async (item) => {
        if (item.preview && !item.preview.startsWith('blob:')) return { ...item }
        try {
          const response = await api.get('/storage/preview-url', {
            params: { object_key: item.key },
          })
          return { ...item, preview: String(response.data.preview_url || '') }
        } catch {
          return { ...item, preview: '' }
        }
      }),
    )
    const settings = draft.settings
    resolution.value = String(settings.resolution ?? resolution.value)
    selectedCharacterIds.value = Array.isArray(settings.selectedCharacterIds)
      ? settings.selectedCharacterIds.map(String)
      : []
    useT2VReferences.value = Boolean(settings.useT2VReferences)
    environmentSource.value = settings.environmentSource === 'official' ? 'official' : 'upload'
    selectedEnvironmentId.value = String(settings.selectedEnvironmentId ?? '')
    minimaxH3Mode.value = ['t2v', 'i2v', 'flf2v'].includes(String(settings.minimaxH3Mode))
      ? settings.minimaxH3Mode as 't2v' | 'i2v' | 'flf2v'
      : 't2v'
    minimaxH3ResolutionPreset.value = ['preview', 'small', 'standard', 'hd'].includes(String(settings.minimaxH3ResolutionPreset))
      ? settings.minimaxH3ResolutionPreset as 'preview' | 'small' | 'standard' | 'hd'
      : 'preview'
    minimaxH3AspectRatio.value = ['16:9', '9:16', '1:1', '4:3', '3:4'].includes(String(settings.minimaxH3AspectRatio))
      ? settings.minimaxH3AspectRatio as '16:9' | '9:16' | '1:1' | '4:3' | '3:4'
      : '16:9'
    minimaxH3ReferenceDescriptions.value = Array.isArray(settings.minimaxH3ReferenceDescriptions)
      ? settings.minimaxH3ReferenceDescriptions.map(String)
      : ['', '', '', '']
    minimaxH3AddonNames.value = Array.isArray(settings.minimaxH3AddonNames)
      ? settings.minimaxH3AddonNames.map(String)
      : []
    minimaxH3AddonItems.value = Array.isArray(settings.minimaxH3AddonItems)
      ? settings.minimaxH3AddonItems as MiniMaxH3AddonItem[]
      : []
    selectedLtxLoraNames.value = Array.isArray(settings.selectedLtxLoraNames)
      ? settings.selectedLtxLoraNames.map(String)
      : []
    ltxLoraItems.value = Array.isArray(settings.ltxLoraItems)
      ? settings.ltxLoraItems as LtxVideoLoraItem[]
      : []
    await nextTick()
    references.clearReferences()
    references.uploadedReferences.value = restoredReferences
  }
  const promptOptimizer = usePromptOptimizer({
    currentModeId,
    prompt,
    duration,
    uploadedReferences: references.uploadedReferences,
    selectedCharacterIds,
    useT2VReferences,
    environmentSource,
    selectedEnvironmentId,
    minimaxH3Mode,
    captureOriginDraft: capturePromptOptimizationDraft,
    applyOriginDraft: restorePromptOptimizationDraft,
  })

  function resetFormState(options?: { preserveMode?: boolean }) {
    references.clearReferences()
    slots.clearSlotAssets()
    prompt.value = ''
    audioPrompt.value = ''
    selectedEditLora.value = ''
    customEditLoraStrength.value = DEFAULT_EDIT_LORA_STRENGTH
    selectedVideoLora.value = getDefaultVideoLoraSelection()
    ltxLoraItems.value = []
    selectedLtxLoraNames.value = []
    minimaxH3AddonNames.value = []
    minimaxH3AddonItems.value = []
    negativePrompt.value = DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT
    wan22ResolutionPreset.value = DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET
    resolution.value = getDefaultResolutionForMode(options?.preserveMode ? currentModeId.value : DEFAULT_LAB_MODE_ID)
    duration.value = DEFAULT_VIDEO_DURATION
    selectedCharacterIds.value = []
    useT2VReferences.value = false
    environmentSource.value = 'official'
    selectedEnvironmentId.value = ''
    template.resetTemplateState()
    wan22.resetWan22ChainState()
    ltx.resetLtxExtensionState()

    if (!options?.preserveMode) {
      currentModeId.value = DEFAULT_LAB_MODE_ID
    }

    setSubmittedTaskId(null)
  }

  const wan22 = useWan22ChainEditor({
    currentModeId,
    currentTask,
    uploadedReferences: references.uploadedReferences,
    prompt,
    negativePrompt,
    wan22ResolutionPreset,
    duration,
    selectedVideoLora,
    resetFormState,
    showDetailRecord: tasksStore.showDetailRecord,
    t,
  })

  const template = useLabTemplateHydration({
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
    applyWan22ChainPrefill: wan22.applyWan22ChainPrefill,
    applyLtxExtensionPrefill: (...args) => ltx.applyLtxExtensionPrefill(...args),
    applySlotTemplateTarget: slots.applySlotTemplateTarget,
    t,
  })

  const ltx = useLtxChainEditor({
    currentModeId,
    currentTask,
    uploadedReferences: references.uploadedReferences,
    prompt,
    clearReferences: references.clearReferences,
    clearSlotAssets: slots.clearSlotAssets,
    resetTemplateState: template.resetTemplateState,
    resetWan22ChainState: wan22.resetWan22ChainState,
    setSubmittedTaskId,
    showDetailRecord: tasksStore.showDetailRecord,
    t,
  })

  const hasReferences = computed(() => references.uploadedReferences.value.length > 0)
  const hasAdvancedOptions = computed(() => currentMode.value.supportsAdvancedOptions)
  const hasStructuredUploadSlots = computed(() => (currentMode.value.uploadSlots?.length ?? 0) > 0)
  const referenceTitle = computed(() =>
    currentMode.value.referenceTitleKey ? t(currentMode.value.referenceTitleKey) : '',
  )
  const promptPlaceholder = computed(() => t(currentMode.value.promptPlaceholderKey))
  const showStructuredPromptInput = computed(() => (
    isScail2ModeId(currentMode.value.id)
  ))
  const composerNotice = computed(() => (
    wan22.wan22ChainBanner.value || ltx.ltxExtensionNotice.value || template.templateNotice.value
  ))
  const composerWarning = computed(() => template.templateWarning.value)

  const videoResolutionOptions = computed(() => (
    currentMode.value.id === 'face_video'
      ? FACE_VIDEO_RESOLUTION_OPTIONS
      : currentMode.value.id === 'ltx_t2v' && selectedCharacterIds.value.length > 0
        ? LTX_T2V_IC_RESOLUTION_OPTIONS
      : isLtxLabModeId(currentMode.value.id)
        ? LTX_VIDEO_RESOLUTION_OPTIONS
        : VIDEO_RESOLUTION_OPTIONS
  ))
  const videoDurationOptions = computed(() => (
    isLtxLabModeId(currentMode.value.id)
      ? LTX_VIDEO_DURATION_OPTIONS
      : isScail2ModeId(currentMode.value.id)
        ? getScail2VideoDurationOptionsForMotionVideo(
            slots.scail2MotionVideoDurationSeconds.value,
            currentMode.value.id,
          )
        : VIDEO_DURATION_OPTIONS
  ))

  const uploadButtonLabel = computed(() => (
    currentMode.value.id === 'ltx_t2v'
      ? t('characters.add_scene_background')
      : (currentMode.value.id === 'wan22_video_v2' || currentMode.value.id === 'custom_video' || currentMode.value.id === 'ltx_video' || currentMode.value.id === 'ltx_video_v2') && references.uploadedReferences.value.length === 0
      ? t('lab.workbench.add_start_frame')
      : (currentMode.value.id === 'wan22_video_v2' || currentMode.value.id === 'custom_video' || currentMode.value.id === 'ltx_video' || currentMode.value.id === 'ltx_video_v2') && references.uploadedReferences.value.length === 1
        ? t('lab.workbench.add_end_frame')
        : currentMode.value.maxImages > 1 && references.uploadedReferences.value.length === 1
          ? t('lab.workbench.add_second_reference')
          : t('lab.workbench.add_reference')
  ))

  const cost = computed(() => getLabModeCost({
    mode: currentMode.value,
    uploadedReferenceCount: references.uploadedReferences.value.length,
    resolution: resolution.value,
    duration: duration.value,
    wan22ResolutionPreset: wan22ResolutionPreset.value,
    hasCharacter: useT2VReferences.value,
  }))
  const displayedCost = computed(() => currentModeId.value === 'minimax_h3'
      ? ({
        preview: 10,
        small: 15,
        standard: 20,
        hd: 30,
      }[minimaxH3ResolutionPreset.value]) * Number(duration.value) / 5
    : cost.value)

  const costHint = computed(() => {
    const key = getLabCostHintKey(currentMode.value.id)
    return key ? t(key) : ''
  })

  const pendingUploads = computed(() => (
    references.pendingReferenceUploadCount.value + slots.pendingSlotUploadCount.value
  ))
  const canSubmit = computed(() => {
    const hasPrompt = !currentMode.value.promptRequired || template.isTemplatePromptLocked.value || prompt.value.trim().length > 0
    const hasRequiredUpload = currentMode.value.id === 'minimax_h3'
      ? minimaxH3Mode.value === 't2v'
        ? references.uploadedReferences.value.length === 0
        : minimaxH3Mode.value === 'i2v'
          ? references.uploadedReferences.value.length === 1
          : references.uploadedReferences.value.length === 2
      : currentMode.value.id === 'ltx_t2v'
      ? !useT2VReferences.value
        ? references.uploadedReferences.value.length === 0
        : selectedCharacterIds.value.length === 2 && (
            environmentSource.value === 'official'
              ? Boolean(selectedEnvironmentId.value) && references.uploadedReferences.value.length === 0
              : references.uploadedReferences.value.length === 1
          )
      : !currentMode.value.supportsUpload || references.uploadedReferences.value.length > 0
    const hasRequiredSlots = slots.assetUploadSlots.value.every(slot => !slot.required || !!slot.item?.key)
    return hasPrompt && hasRequiredUpload && hasRequiredSlots && pendingUploads.value === 0 && !uploading.value
  })

  const isDirty = computed(() => (
    prompt.value.trim().length > 0
    || audioPrompt.value.trim().length > 0
    || references.uploadedReferences.value.length > 0
    || Object.keys(slots.uploadedSlotAssets.value).length > 0
    || selectedEditLora.value !== ''
    || selectedVideoLora.value !== getDefaultVideoLoraSelection()
    || selectedLtxLoraNames.value.length > 0
    || minimaxH3AddonNames.value.length > 0
    || negativePrompt.value !== DEFAULT_WAN22_VIDEO_V2_NEGATIVE_PROMPT
    || wan22ResolutionPreset.value !== DEFAULT_WAN22_VIDEO_V2_RESOLUTION_PRESET
    || wan22.wan22ChainMode.value !== 'default'
    || resolution.value !== getDefaultResolutionForMode(currentModeId.value)
    || duration.value !== DEFAULT_VIDEO_DURATION
    || template.isTemplateApplied.value
    || selectedCharacterIds.value.length > 0
    || useT2VReferences.value
  ))

  watch(selectedEditLora, (nextValue) => {
    if (template.isTemplateEditSettingsLocked.value) {
      return
    }

    customEditLoraStrength.value = nextValue
      ? (EDIT_LORA_DEFAULT_STRENGTHS[nextValue] ?? DEFAULT_EDIT_LORA_STRENGTH)
      : DEFAULT_EDIT_LORA_STRENGTH
  })

  watch(minimaxH3AddonNames, (names) => {
    const validNames = names.filter(name => (
      MINIMAX_H3_ADDON_OPTIONS.some(option => option.value === name)
    ))
    const currentByName = new Map(
      minimaxH3AddonItems.value.map(item => [item.name, item.strength]),
    )
    minimaxH3AddonItems.value = validNames.map((name) => {
      const option = MINIMAX_H3_ADDON_OPTIONS.find(item => item.value === name)!
      return {
        name,
        strength: currentByName.get(name) ?? option.defaultStrength,
      }
    })
  }, { deep: true })

  watch(videoDurationOptions, (options) => {
    if (!isScail2ModeId(currentMode.value.id)) {
      return
    }
    if (!options.some(option => option.value === duration.value)) {
      duration.value = options[0]?.value ?? DEFAULT_VIDEO_DURATION
    }
  }, { immediate: true })

  watch(selectedCharacterIds, (characterIds) => {
    if (currentMode.value.id !== 'ltx_t2v') return
    resolution.value = characterIds.length > 0 ? '768x448' : '1280x704'
  })
  watch(useT2VReferences, (enabled) => {
    if (!enabled) {
      selectedCharacterIds.value = []
      selectedEnvironmentId.value = ''
      references.clearReferences()
    }
  })
  watch(environmentSource, () => {
    selectedEnvironmentId.value = ''
    references.clearReferences()
  })

  watch(
    () => [
      route.query.type,
      route.query.apply,
      route.query.wan22_mode,
      route.query.wan22_task_id,
      route.query.ltx_extend_key,
      route.query.ltx_extend_url,
      route.query.ltx_extend_task_id,
      route.query.ltx_chain_task_ids,
    ],
    template.hydrateFromRoute,
    { immediate: true },
  )

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

  const { handleSubmit } = useLabSubmitPayload({
    currentMode,
    hasStructuredUploadSlots,
    assetUploadSlots: slots.assetUploadSlots,
    uploadedReferences: references.uploadedReferences,
    uploadedSlotAssets: slots.uploadedSlotAssets,
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
    minimaxH3ReferenceDescriptions,
    minimaxH3AddonItems,
    isTemplateApplied: template.isTemplateApplied,
    isTemplatePromptLocked: template.isTemplatePromptLocked,
    templateSourcePostId: template.templateSourcePostId,
    wan22PrevTaskId: wan22.wan22PrevTaskId,
    wan22ChainTaskIds: wan22.wan22ChainTaskIds,
    ltxPrevTaskId: ltx.ltxPrevTaskId,
    ltxChainTaskIds: ltx.ltxChainTaskIds,
    submitTask,
    setSubmittedTaskId,
    t,
  })

  const resetAfterResult = () => {
    resetFormState({ preserveMode: true })
  }

  onBeforeUnmount(() => {
    references.clearReferences()
    slots.clearSlotAssets()
  })

  return {
    unifiedModes,
    currentMode,
    currentModeId,
    prompt,
    audioPrompt,
    uploadedReferences: references.uploadedReferences,
    displayedReferences: references.displayedReferences,
    assetUploadSlots: slots.assetUploadSlots,
    canUploadReference: references.canUploadReference,
    promptPlaceholder,
    showStructuredPromptInput,
    isSubmitting,
    currentTask,
    isImageUrl,
    downloadResult,
    selectMode,
    beforeUpload: references.beforeUpload,
    beforeUploadSlot: slots.beforeUploadSlot,
    handleAssetVideoMetadata: slots.handleAssetVideoMetadata,
    handleRemoveReference: references.handleRemoveReference,
    handleRemoveUploadSlot: slots.handleRemoveUploadSlot,
    handleSubmit,
    resetAfterResult,
    cost: displayedCost,
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
    selectedCharacterIds,
    useT2VReferences,
    environmentSource,
    selectedEnvironmentId,
    minimaxH3Mode,
    minimaxH3ResolutionPreset,
    minimaxH3AspectRatio,
    minimaxH3ReferenceDescriptions,
    minimaxH3AddonOptions,
    minimaxH3AddonNames,
    minimaxH3AddonItems,
    templateNotice: template.templateNotice,
    templateWarning: template.templateWarning,
    composerNotice,
    composerWarning,
    isTemplateApplied: template.isTemplateApplied,
    isTemplatePromptLocked: template.isTemplatePromptLocked,
    isTemplateEditSettingsLocked: template.isTemplateEditSettingsLocked,
    isTemplateVideoSettingsLocked: template.isTemplateVideoSettingsLocked,
    currentTaskIsWan22VideoV2: wan22.currentTaskIsWan22VideoV2,
    wan22CurrentTaskCanExtend: wan22.wan22CurrentTaskCanExtend,
    wan22CurrentTaskCanStitch: wan22.wan22CurrentTaskCanStitch,
    currentTaskIsLtxVideo: ltx.currentTaskIsLtxVideo,
    ltxCurrentTaskCanExtend: ltx.ltxCurrentTaskCanExtend,
    ltxCurrentTaskCanStitch: ltx.ltxCurrentTaskCanStitch,
    wan22ChainLoading: wan22.wan22ChainLoading,
    wan22ChainStitching: wan22.wan22ChainStitching,
    ltxChainStitching: ltx.ltxChainStitching,
    ...promptOptimizer,
    openWan22CurrentTaskEditor: wan22.openWan22CurrentTaskEditor,
    openLtxCurrentTaskEditor: ltx.openLtxCurrentTaskEditor,
    stitchCurrentWan22Chain: wan22.stitchCurrentWan22Chain,
    stitchCurrentLtxChain: ltx.stitchCurrentLtxChain,
  }
}
